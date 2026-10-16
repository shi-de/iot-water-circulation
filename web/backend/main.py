import logging
import json
import os
import time
import random
from pathlib import Path
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles   # 修复：静态文件支持，访问前端页面
import paho.mqtt.client as mqtt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
# 本地模块导入
from init_db import init_database
from models import Telemetry, AlarmLog, ControlLog
from payload_adapter import alarm_text_from_code, normalize_device_payload
from config import load_settings
from temperature_alarm import TemperatureAlarmService, TemperatureThresholdError

# --------------------------日志配置--------------------------
# INFO级别日志，记录运行、MQTT收发、报错
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# --------------------------状态文本映射，给前端展示 --------------------------
CMD_STATUS_MAP = {
    "pending": "待设备应答",
    "accepted": "设备已接收",
    "rejected": "设备拒绝执行",
    "executed": "执行完成",
    "expired": "命令已过期"
}

# --------------------------赛场配置（config.json，可由环境变量覆盖）--------------------------
SETTINGS = load_settings()
MQTT_BROKER = SETTINGS.mqtt_broker
MQTT_PORT = SETTINGS.mqtt_port
MQTT_TOPIC_SUB = SETTINGS.mqtt_topic_sub
MQTT_TOPIC_PUB = SETTINGS.mqtt_topic_pub
MQTT_CLIENT_ID = SETTINGS.mqtt_client_id
MQTT_USER = SETTINGS.mqtt_user
MQTT_PASS = SETTINGS.mqtt_password
DEVICE_ID = SETTINGS.device_id
FLOW_MIN = SETTINGS.flow_min_lpm
PRESSURE_MAX = SETTINGS.pressure_max_kpa
TEMPERATURE_MAX = SETTINGS.temperature_max_c
TEMPERATURE_MIN = SETTINGS.temperature_min_c

def redact_payload(value):
    """Remove credential-like fields before values reach logs or the web UI."""
    secret_keys = {"password", "passwd", "pass", "mqtt_pass", "mqtt_password", "token", "secret"}
    if isinstance(value, dict):
        return {
            key: "[redacted]" if str(key).lower() in secret_keys else redact_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    return value

# --------------------------SQLite数据库配置--------------------------
# 数据库文件存放在backend文件夹下 water.db
engine = create_engine(
    "sqlite:///./water.db",
    connect_args={"check_same_thread": False}  # sqlite多线程访问开关，MQTT后台线程读写数据库必须开启
)
# 创建数据库会话工厂，每次数据库操作打开一个session
SessionLocal = sessionmaker(bind=engine)
temperature_alarm_service = TemperatureAlarmService(
    SessionLocal,
    defaults=(TEMPERATURE_MIN, TEMPERATURE_MAX),
)

# --------------------------全局内存缓存【对接前端页面关键】--------------------------
# 保存最新一帧设备数据，用于/api/v1/status接口返回给前端页面
# MQTT每收到一条硬件上报，就更新这个字典，前端不需要查数据库就能拿到最新状态
g_latest_device = {
    "temp1": None,
    "temp2": None,
    "temperature": None,
    "pressure": None,
    "flow": None,
    "pump_state": 0,
    "heat_state": 0,
    "alarm": 0,
    "online": False,
    "last_update": "",
    "device_id": DEVICE_ID,
    "fault_text": "",
    "mode": "manual",
    "raw": {}
}

# --------------------------生成唯一command_id工具函数 --------------------------
def gen_command_id() -> str:
    """生成唯一命令ID：时间戳+随机，避免重复"""
    t = int(time.time() * 1000)
    r = random.randint(0, 999)
    return f"{t}_{r}"
# --------------------------扫描并标记过期命令 --------------------------
def scan_expired_commands():
    """把pending状态、已经超过expire_time的记录标记为expired"""
    now = datetime.now()
    with SessionLocal() as session:
        records = session.query(ControlLog).filter(
            ControlLog.status == "pending",
            # ControlLog.expire_time < now
        ).all()
        for rec in records:
         # 动态计算过期时刻：下发时间 + expire_after秒
            send_dt = rec.timestamp
            expire_sec = rec.expire_after if rec.expire_after is not None else 5
            expire_dt = send_dt + timedelta(seconds=expire_sec)
            if now > expire_dt:
                rec.status = "expired"
        session.commit()

# --------------------------全局MQTT客户端对象--------------------------
g_mqtt_connected = False
g_mqtt_last_message_at = None
g_mqtt_last_connect_rc = None
g_mqtt_last_disconnect_rc = None
g_mqtt_connect_count = 0

def create_mqtt_client(client_factory=mqtt.Client):
    client = client_factory(client_id=MQTT_CLIENT_ID)
    if MQTT_USER or MQTT_PASS:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.reconnect_delay_set(1, 10)
    return client

mqtt_client = create_mqtt_client()


def start_mqtt_client(client=mqtt_client):
    """Start the network loop even when the broker is initially unavailable."""
    logger.info(
        f"正在连接MQTT Broker {MQTT_BROKER}:{MQTT_PORT}，"
        f"订阅主题 {MQTT_TOPIC_SUB}"
    )
    client.connect_async(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_start()


def build_alarm_faults(
    flow=None,
    pressure=None,
    alarm_code=0,
    temp1=None,
    temp2=None,
):
    """Return alarm text together with the value and limit that triggered it."""
    faults = []
    if flow is not None and flow < FLOW_MIN:
        faults.append(("水流量过低", flow, FLOW_MIN))
    if pressure is not None and pressure >= PRESSURE_MAX:
        faults.append(("水压力超限", pressure, PRESSURE_MAX))
    if temp1 is not None and temp1 > TEMPERATURE_MAX:
        faults.append(("进水温度超上限", temp1, TEMPERATURE_MAX))
    if temp2 is not None and temp2 > TEMPERATURE_MAX:
        faults.append(("出水温度超上限", temp2, TEMPERATURE_MAX))
    if temp1 is not None and temp1 < TEMPERATURE_MIN:
        faults.append(("进水温度超下限", temp1, TEMPERATURE_MIN))
    if temp2 is not None and temp2 < TEMPERATURE_MIN:
        faults.append(("出水温度超下限", temp2, TEMPERATURE_MIN))
    if alarm_code != 0:
        faults.append((alarm_text_from_code(alarm_code), float(alarm_code), 0.0))
    return faults


def _parse_local_datetime(value, field_name):
    if value is None or value == "":
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{field_name}格式无效") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed.replace(microsecond=0)


def publish_control_payload(payload_json):
    """Publish a control payload only when the MQTT connection is usable."""
    if not mqtt_client.is_connected():
        raise HTTPException(status_code=503, detail="MQTT服务未连接，控制指令未发送")
    try:
        result = mqtt_client.publish(MQTT_TOPIC_PUB, payload_json)
    except Exception as exc:
        logger.error(f"MQTT控制发布异常: {exc}")
        raise HTTPException(status_code=503, detail="MQTT控制发布失败") from exc
    if result is None or result.rc != mqtt.MQTT_ERR_SUCCESS:
        rc = getattr(result, "rc", "unknown")
        logger.error(f"MQTT控制发布失败，返回码:{rc}")
        raise HTTPException(status_code=503, detail="MQTT控制发布失败")
    return result

def on_connect(client, userdata, flags, rc):
    """收到broker CONNACK后再订阅，避免启动日志误报连接成功。"""
    global g_mqtt_connected, g_mqtt_last_connect_rc, g_mqtt_connect_count
    rc_value = int(rc)
    g_mqtt_last_connect_rc = rc_value
    if rc_value == 0:
        g_mqtt_connected = True
        g_mqtt_connect_count += 1
        subscribe_result = client.subscribe(MQTT_TOPIC_SUB)
        subscribe_rc = subscribe_result[0] if subscribe_result is not None else "unknown"
        logger.info(
            f"MQTT on_connect rc={rc_value} connect_count={g_mqtt_connect_count} "
            f"subscribe_rc={subscribe_rc} topic={MQTT_TOPIC_SUB} "
            f"last_packet={g_mqtt_last_message_at or 'never'}"
        )
    else:
        g_mqtt_connected = False
        logger.error(
            f"MQTT on_connect rc={rc_value} rejected "
            f"last_packet={g_mqtt_last_message_at or 'never'}"
        )

def on_message(client, userdata, msg):
    """
    MQTT回调函数：当EMQX收到硬件发布消息，自动触发这个函数（运行在MQTT后台线程）
    :param client: mqtt客户端实例
    :param userdata: 用户自定义数据
    :param msg: mqtt消息对象，包含主题、二进制payload
    """
    global g_latest_device, g_mqtt_last_message_at
    g_mqtt_last_message_at = datetime.now().isoformat()
    try:
        # 将二进制字节payload解码为utf‑8字符串，再解析json字典
        payload = json.loads(msg.payload.decode("utf-8"))
        logger.info(f"收到MQTT设备上报: {redact_payload(payload)}")
        now_dt = datetime.now()

        # 每收到一帧上报，顺带扫描过期命令
        scan_expired_commands()

        # =========处理STM32回传的ACK应答 =========
        ack_info = payload.get("ack")
        if ack_info and isinstance(ack_info, dict):
            ack_cmd_id = ack_info.get("command_id")
            ack_status_dev = ack_info.get("status")
            # valid_status = {"accept", "reject", "done"}
            dev_ack_map = {
                "accept":"accepted",
                "reject":"rejected",
                "done":"executed"
            }
            if ack_cmd_id is not None and ack_status_dev in dev_ack_map:
                backend_status = dev_ack_map[ack_status_dev]
                with SessionLocal() as session:
                    rec = session.query(ControlLog).filter(ControlLog.command_id == ack_cmd_id).first()
                    if rec:
                        now_dt = datetime.now()
                        send_dt = rec.timestamp
                        expire_dt = send_dt + timedelta(seconds=rec.expire_after)
                        # 没有过期，并且当前状态还是pending，才更新ack
                        if now_dt <= expire_dt and rec.status == "pending":
                            rec.ack_at = now_dt
                            rec.status = backend_status
                            rec.ack_result = json.dumps(ack_info,ensure_ascii=False)
                            logger.info(f"收到命令应答 command_id={ack_cmd_id}, status={backend_status}")
                        session.commit()
        # ========= 1. 收集报警及其真实触发值/阈值 =========
        new_state = normalize_device_payload(
            payload,
            previous_mode=g_latest_device["mode"],
            previous_state=g_latest_device,
            default_device_id=DEVICE_ID,
        )
        flow_val = new_state.get("flow")
        pressure_val = new_state.get("pressure")
        alarm_code = new_state["alarm"]
        faults = build_alarm_faults(
            flow_val,
            pressure_val,
            alarm_code,
            None,
            None,
        )
        new_state["raw"] = redact_payload(payload)
        fault_text = ";".join(item[0] for item in faults)

        # ========= 2. 构造完整新状态字典，一次性原子赋值，消除帧撕裂 =========
        if fault_text:
            new_state["fault_text"] = fault_text
        # 一次性替换全局对象，原子操作，不会读到半更新数据
        g_latest_device = new_state

        # =========数据库写入=========
        with SessionLocal() as session:
            telemetry = Telemetry(
                device_id=new_state["device_id"],
                seq=new_state.get("seq"),
                timestamp=datetime.now(),
                temp1=new_state.get("temp1"),
                temp2=new_state.get("temp2"),
                temperature=new_state.get("temperature"),
                pressure=new_state.get("pressure"),
                flow=new_state.get("flow"),
                pump_state=new_state.get("pump_state", 0),
                heat_state=new_state.get("heat_state", 0),
                alarm=new_state.get("alarm", 0),
                mode=new_state.get("mode", "manual"),
                fault_text=new_state.get("fault_text", ""),
                raw_json=json.dumps(payload, ensure_ascii=False)
            )
            session.add(telemetry)
            # 将每一条报警写入报警日志
            for msg, value, threshold in faults:
                alarm = AlarmLog(
                    device_id=new_state["device_id"],
                    alarm_type="安全联锁",
                    code=alarm_code,
                    level="error" if alarm_code else "warn",
                    msg=msg,
                    value=value,
                    threshold=threshold,
                    active=True,
                    raw_json=json.dumps(payload, ensure_ascii=False)
                )
                session.add(alarm)
            telemetry_saved = False
            try:
                session.commit()
                telemetry_saved = True
            except IntegrityError:
                # device_id + seq重复，属于重复上报，直接丢弃本条遥测，不抛异常
                session.rollback()
                logger.warning(f"重复报文丢弃 device_id={new_state['device_id']} seq={payload.get('seq')}")

        if telemetry_saved:
            try:
                temperature_alarm_service.process_temp2(
                    new_state["device_id"], new_state.get("temp2"), now_dt
                )
            except Exception as exc:
                logger.error("出水温度报警处理失败: %s", exc, exc_info=True)

    except Exception as e:
        logger.error(f"MQTT消息处理失败: {e}", exc_info=True)

def on_disconnect(client, userdata, rc):
    """MQTT断开回调，打印日志，提示断开，可以在这里扩展自动重连逻辑"""
    global g_latest_device, g_mqtt_connected, g_mqtt_last_disconnect_rc
    rc_value = int(rc)
    g_mqtt_last_disconnect_rc = rc_value
    g_mqtt_connected = False
    g_latest_device = {
        **g_latest_device,
        "online": False,
        "fault_text": "MQTT连接断开"
    }
    log = logger.warning if rc_value != 0 else logger.info
    log(
        f"MQTT on_disconnect rc={rc_value} "
        f"last_packet={g_mqtt_last_message_at or 'never'} "
        f"auto_reconnect={'yes' if rc_value != 0 else 'no'}"
    )

# 绑定回调函数
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.on_disconnect = on_disconnect

# --------------------------FastAPI生命周期管理 lifespan --------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    lifespan：应用启动/关闭钩子，替代旧版startup/shutdown事件
    yield之前 = 服务启动执行；yield之后 = 服务关闭执行
    """
    # =========服务启动阶段=========
    # 1. 自动初始化数据库，没有表就创建；已有表不会删除数据
    init_database()
    logger.info("数据库初始化完成")
    try:
        start_mqtt_client()
    except Exception as e:
        logger.error(f"MQTT网络循环启动失败，错误:{e}")

    yield  # 应用正式运行，接收http请求

    # =========服务关闭阶段=========
    mqtt_client.disconnect()
    mqtt_client.loop_stop()
    logger.info("MQTT已断开，服务即将退出")

# 创建FastAPI实例，挂载生命周期钩子
app = FastAPI(lifespan=lifespan, title="水循环技能赛后端(MQTT版)")

# 挂载static静态文件夹，浏览器访问前端页面 http://127.0.0.1:8000/static/index.html
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).resolve().parent.parent / "static"),
    name="static",
)

# --------------------------接口定义--------------------------
@app.get("/health")
def health_check():
    """健康检查接口，裁判检测服务是否存活"""
    return {"status":"ok"}

@app.get("/api/v1/status")
def get_status():
    """
    【前端页面每秒轮询这个接口！】
    返回最新一帧设备状态数据，取自全局内存g_latest_device，不需要查数据库，速度快
    对接之前写好的index.html前端可视化页面
    """
    return {
        **g_latest_device,
        "mqtt_broker": MQTT_BROKER,
        "mqtt_port": MQTT_PORT,
        "mqtt_topic": MQTT_TOPIC_SUB,
        "mqtt_connected": g_mqtt_connected,
        "mqtt_last_connect_rc": g_mqtt_last_connect_rc,
        "mqtt_last_disconnect_rc": g_mqtt_last_disconnect_rc,
        "mqtt_connect_count": g_mqtt_connect_count,
        "mqtt_last_message_at": g_mqtt_last_message_at,
        "config": SETTINGS.public_dict(),
    }


@app.get("/api/v1/telemetry")
def get_telemetry(limit: int = 100, device_id: str = None,
                  start: str = None, end: str = None):
    with SessionLocal() as session:
        q = session.query(Telemetry)
        if device_id:
            q = q.filter(Telemetry.device_id == device_id)
        if start:
            try:
                from datetime import datetime
                start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                q = q.filter(Telemetry.timestamp >= start_dt)
            except ValueError:
                pass
        if end:
            try:
                from datetime import datetime
                end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
                q = q.filter(Telemetry.timestamp <= end_dt)
            except ValueError:
                pass
        rows = q.order_by(Telemetry.timestamp.desc()).limit(limit).all()
        result_list = []
        for r in rows:
            result_list.append({
                "timestamp": r.timestamp.isoformat(),
                "temp1": r.temp1,
                "temp2": r.temp2,
                "pressure": r.pressure,
                "flow": r.flow,
                "device_id": r.device_id
            })
        return {"count": len(result_list), "rows": result_list}


class TemperatureThresholdRequest(BaseModel):
    minimum_c: float
    maximum_c: float


@app.get("/api/v1/temperature-thresholds")
def get_temperature_thresholds():
    return temperature_alarm_service.get_thresholds()


@app.put("/api/v1/temperature-thresholds")
def put_temperature_thresholds(body: TemperatureThresholdRequest):
    try:
        return temperature_alarm_service.update_thresholds(body.minimum_c, body.maximum_c)
    except TemperatureThresholdError as exc:
        raise HTTPException(
            status_code=exc.http_status,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


@app.get("/api/v1/alarms")
def get_alarms(
    start: str = None,
    end: str = None,
    limit: int = 50,
    offset: int = 0,
):
    """查询出水温度上下限报警；固件原始报警仍保留在实时状态。"""
    try:
        return temperature_alarm_service.query_alarms(
            _parse_local_datetime(start, "报警开始时间"),
            _parse_local_datetime(end, "报警结束时间"),
            limit,
            offset,
        )
    except TemperatureThresholdError as exc:
        raise HTTPException(
            status_code=exc.http_status,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

@app.get("/api/v1/controls")
def get_controls(limit: int = 50):
    """获取控制记录，返回映射后的人类可读状态文本，前端页面直接展示"""
    with SessionLocal() as session:
        records = session.query(ControlLog).order_by(ControlLog.timestamp.desc()).limit(limit).all()
        result = []
        for r in records:
            try:
                command = json.loads(r.cmd or "{}")
            except (TypeError, json.JSONDecodeError):
                command = {}
            summaries = []
            if "pump" in command:
                summaries.append(f"水泵：{'开启' if int(command['pump']) else '关闭'}")
            if "heater" in command or "heat" in command:
                heat = command.get("heater", command.get("heat"))
                summaries.append(f"加热：{'开启' if int(heat) else '关闭'}")
            if "mode" in command:
                summaries.append(f"模式：{'自动' if command['mode'] == 'auto' else '手动'}")
            result.append({
                "id": r.id,
                "command_id": r.command_id,
                "send_time": r.timestamp.isoformat() if r.timestamp else None,
                "cmd": r.cmd,
                "cmd_summary": "；".join(summaries) or r.cmd,
                "status": r.status,
                "status_text": CMD_STATUS_MAP.get(r.status, "--"),
                "result": r.result,
                "ack_result": r.ack_result,
                "ack_at": r.ack_at.isoformat(timespec="seconds") if r.ack_at else None,
            })
    return result


@app.post("/api/v1/control")
def control_device(cmd: dict):
    """
    前端按钮点击调用这个接口，下发MQTT控制指令给ESP‑01S硬件
    请求体示例 {"pump":1,"heat":0}
    """
    global g_latest_device
    try:
        # 取出expire_after，限制合法范围
        expire_after = int(cmd.pop("expire_after", 5))
        expire_after = max(1, min(60, expire_after))

        cmd_id = gen_command_id() # 现在返回字符串
        send_dt = datetime.now()

        # 组装下发给硬件的完整报文（带上command_id、expire_after）
        mqtt_payload = {
            "command_id": cmd_id,
            "expire_after": expire_after,
            **cmd
        }
        payload_json = json.dumps(mqtt_payload)
        # MQTT发布，未连上或发布失败时不记录为已发送
        publish_control_payload(payload_json)

        # 更新内存mode状态，如果指令携带mode
        if "mode" in cmd:
            g_latest_device = {**g_latest_device, "mode": cmd["mode"]}

        # 写入数据库控制日志，初始状态pending，等待STM32回传ack
        with SessionLocal() as session:
            log_rec = ControlLog(
                command_id=cmd_id,
                device_id=g_latest_device["device_id"],
                timestamp=send_dt, # 模型字段叫timestamp，不是send_time
                expire_after=expire_after,
                cmd=payload_json,
                status="pending", # 模型字段 status，不是ack_status
                result="sent",
                raw_json=payload_json
            )
            session.add(log_rec)
            session.commit()

        return {"ok": True, "command_id": cmd_id, "send_cmd": mqtt_payload}

    except Exception as e:
        logger.error(f"控制下发失败: {e}")
        raise HTTPException(status_code=500, detail="控制指令下发失败")
