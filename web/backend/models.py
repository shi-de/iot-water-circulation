# backend/models.py
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    DateTime,
    Boolean,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Telemetry(Base):
    """遥测数据表：HTTP/MQTT 上报的传感器和执行器状态都存这里。"""
    __tablename__ = "telemetry"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 设备与去重
    device_id = Column(String(64), nullable=False, default="esp32-01", index=True)
    seq = Column(Integer, nullable=True, index=True)          # 设备上报序号，配合 device_id 去重
    timestamp = Column(DateTime, default=datetime.now, index=True)  # 设备上报时间/业务时间
    received_at = Column(DateTime, default=datetime.now)      # 服务器接收时间

    # 温度
    temp1 = Column(Float)          # DS18B20 温度1
    temp2 = Column(Float)          # DS18B20 温度2
    temperature = Column(Float)    # 兼容旧字段，可存主温度或平均温度

    # 压力、流量
    pressure = Column(Float)       # kPa
    flow = Column(Float)           # L/min

    # 执行器状态
    pump_state = Column(Integer, default=0)   # 0=停，1=运行
    heat_state = Column(Integer, default=0)   # 0=关，1=加热

    # 报警
    alarm = Column(Integer, default=0)        # 报警码，0=正常
    mode = Column(String(16), default="manual")  # auto / manual
    fault_text = Column(Text, default="")     # 故障文本

    # 原始报文
    raw_json = Column(Text, default="")

    __table_args__ = (
        UniqueConstraint("device_id", "seq", name="uq_telemetry_device_seq"),
        Index("ix_telemetry_device_ts", "device_id", "timestamp"),
    )


class ControlLog(Base):
    """控制命令日志：记录下发、过期、设备 ACK。"""
    __tablename__ = "control_log"

    id = Column(Integer, primary_key=True, autoincrement=True)

    command_id = Column(String(64), unique=True, index=True)  # 命令唯一编号
    device_id = Column(String(64), index=True)                # 目标设备
    timestamp = Column(DateTime, default=datetime.now, index=True)

    expire_after = Column(Integer, default=5)                 # 过期秒数
    cmd = Column(Text, nullable=False, default="{}")          # 命令 JSON
    status = Column(String(16), default="pending")            # pending/accepted/rejected/executed/expired
    result = Column(String(32), default="ok")                 # 兼容旧字段
    ack_result = Column(Text, default="")                     # 设备回传内容
    ack_at = Column(DateTime)                                 # 设备 ACK 时间
    raw_json = Column(Text, default="")


class AlarmLog(Base):
    """报警日志：安全联锁、报警恢复、裁判查看。"""
    __tablename__ = "alarm_log"

    id = Column(Integer, primary_key=True, autoincrement=True)

    device_id = Column(String(64), index=True)
    timestamp = Column(DateTime, default=datetime.now, index=True)

    alarm_type = Column(String(64))       # 报警类型：流量过低、压力超限、温度断线等
    code = Column(Integer, default=0)     # 报警码
    level = Column(String(16), default="warn")  # info / warn / error
    msg = Column(Text)                    # 报警描述

    value = Column(Float)                 # 触发值
    threshold = Column(Float)             # 阈值
    active = Column(Boolean, default=True)  # 是否仍在报警
    cleared_at = Column(DateTime)           # 恢复时间

    raw_json = Column(Text, default="")


class TemperatureThreshold(Base):
    __tablename__ = "temperature_threshold"

    id = Column(Integer, primary_key=True, default=1)
    minimum_c = Column(Float, nullable=False, default=0.0)
    maximum_c = Column(Float, nullable=False, default=60.0)
    updated_at = Column(DateTime, nullable=False, default=datetime.now)
