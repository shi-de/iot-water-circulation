from datetime import datetime
import math


def _valid_temperature(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and -55.0 <= value <= 125.0
        and value != -99.0
    )


def _previous_temperature(previous_state, key):
    value = (previous_state or {}).get(key)
    return value if _valid_temperature(value) else None


def alarm_text_from_code(alarm_code: int) -> str:
    """把单片机报警码翻译成适合前端展示的中文文本。"""
    alarm_map = {
        0: "",
        1: "温度传感器异常",
        2: "压力超限",
        3: "流量不足或水泵空转",
        4: "温度超限",
    }
    return alarm_map.get(alarm_code, f"未知报警码:{alarm_code}")


def normalize_device_payload(
    payload: dict,
    previous_mode: str = "manual",
    previous_state: dict | None = None,
    default_device_id: str = "watercycle-001",
) -> dict:
    """
    兼容当前已调通的ESP上报格式：
    {"device":"esp-manual-test","temperature":25.63,"pressure":32.70,
     "flow":21.87,"pump":1,"heater":1,"alarm":0}
    """
    raw_temperature = payload.get("temperature")
    raw_temp1 = payload["temp1"] if "temp1" in payload else raw_temperature
    raw_temp2 = payload["temp2"] if "temp2" in payload else raw_temperature
    temp1 = raw_temp1 if _valid_temperature(raw_temp1) else _previous_temperature(previous_state, "temp1")
    temp2 = raw_temp2 if _valid_temperature(raw_temp2) else _previous_temperature(previous_state, "temp2")
    if _valid_temperature(raw_temperature):
        temperature = raw_temperature
    elif _valid_temperature(temp2):
        temperature = temp2
    elif _valid_temperature(temp1):
        temperature = temp1
    else:
        temperature = _previous_temperature(previous_state, "temperature")
    pressure = payload.get("pressure")
    flow = payload.get("flow")
    pump_state = int(payload.get("pump", payload.get("pump_state", 0)) or 0)
    heat_state = int(payload.get("heater", payload.get("heat_state", 0)) or 0)
    alarm_code = int(payload.get("alarm", 0) or 0)

    fault_text = alarm_text_from_code(alarm_code)
    return {
        "seq": payload.get("seq"),
        "temp1": temp1,
        "temp2": temp2,
        "temperature": temperature,
        "pressure": pressure,
        "flow": flow,
        "pump_state": pump_state,
        "heat_state": heat_state,
        "alarm": alarm_code,
        "online": True,
        "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "device_id": payload.get("device", payload.get("device_id", default_device_id)),
        "fault_text": fault_text,
        "mode": payload.get("mode", previous_mode),
        "raw": payload,
    }
