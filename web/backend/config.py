"""Validated runtime configuration for the water-cycle backend."""

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path


class ConfigError(ValueError):
    """Raised when a configured value is unsafe or malformed."""


DEFAULTS = {
    "mqtt_broker": "192.0.2.10",
    "mqtt_port": 1883,
    "mqtt_topic_sub": "watercycle/device/telemetry",
    "mqtt_topic_pub": "watercycle/device/control",
    "mqtt_client_id": "watercycle-backend-001",
    "mqtt_user": "",
    "mqtt_password": "",
    "device_id": "watercycle-001",
    "flow_min_lpm": 0.50,
    "pressure_max_kpa": 500.0,
    "temperature_min_c": 0.0,
    "temperature_max_c": 60.0,
}

ENV_NAMES = {
    "mqtt_broker": "MQTT_BROKER",
    "mqtt_port": "MQTT_PORT",
    "mqtt_topic_sub": "MQTT_TOPIC_SUB",
    "mqtt_topic_pub": "MQTT_TOPIC_PUB",
    "mqtt_client_id": "MQTT_CLIENT_ID",
    "mqtt_user": "MQTT_USER",
    "mqtt_password": "MQTT_PASS",
    "device_id": "DEVICE_ID",
    "flow_min_lpm": "FLOW_MIN_LPM",
    "pressure_max_kpa": "PRESSURE_MAX_KPA",
    "temperature_min_c": "TEMPERATURE_MIN_C",
    "temperature_max_c": "TEMPERATURE_MAX_C",
}


@dataclass(frozen=True)
class Settings:
    mqtt_broker: str
    mqtt_port: int
    mqtt_topic_sub: str
    mqtt_topic_pub: str
    mqtt_client_id: str
    mqtt_user: str
    mqtt_password: str
    device_id: str
    flow_min_lpm: float
    pressure_max_kpa: float
    temperature_min_c: float
    temperature_max_c: float

    def public_dict(self) -> dict:
        return {
            "mqtt": {
                "broker": self.mqtt_broker,
                "port": self.mqtt_port,
                "telemetry_topic": self.mqtt_topic_sub,
                "control_topic": self.mqtt_topic_pub,
                "device_id": self.device_id,
            },
            "thresholds": {
                "flow_min_for_heating": self.flow_min_lpm,
                "pressure_max": self.pressure_max_kpa,
                "temperature_min": self.temperature_min_c,
                "temperature_max": self.temperature_max_c,
            },
            "units": {
                "temp1": "°C",
                "temp2": "°C",
                "temperature": "°C",
                "pressure": "kPa",
                "flow": "L/min",
            },
        }


def _number(value, name, *, minimum=None, maximum=None):
    if isinstance(value, bool):
        raise ConfigError(f"{name} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} must be a number") from exc
    if not math.isfinite(number):
        raise ConfigError(f"{name} must be finite")
    if minimum is not None and number < minimum:
        raise ConfigError(f"{name} must be at least {minimum}")
    if maximum is not None and number > maximum:
        raise ConfigError(f"{name} must be at most {maximum}")
    return number


def _required_text(value, name):
    text = str(value).strip()
    if not text:
        raise ConfigError(f"{name} must not be empty")
    return text


def load_settings(environ=None, config_path=None) -> Settings:
    environ = os.environ if environ is None else environ
    path = (
        Path(config_path)
        if config_path is not None
        else Path(environ.get("WATER_CONFIG_FILE", Path(__file__).with_name("config.json")))
    )
    values = dict(DEFAULTS)
    if path.exists():
        try:
            file_values = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"cannot read configuration file {path}: {exc}") from exc
        if not isinstance(file_values, dict):
            raise ConfigError("configuration file root must be an object")
        unknown = sorted(set(file_values) - set(DEFAULTS))
        if unknown:
            raise ConfigError(f"unknown configuration key: {unknown[0]}")
        values.update(file_values)

    for key, env_name in ENV_NAMES.items():
        if env_name in environ:
            value = environ[env_name]
            values[key] = value

    broker = _required_text(values["mqtt_broker"], "MQTT_BROKER")
    try:
        port = int(values["mqtt_port"])
    except (TypeError, ValueError) as exc:
        raise ConfigError("MQTT_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ConfigError("MQTT_PORT must be between 1 and 65535")

    telemetry_topic = _required_text(values["mqtt_topic_sub"], "MQTT_TOPIC_SUB")
    control_topic = _required_text(values["mqtt_topic_pub"], "MQTT_TOPIC_PUB")
    if any(char in telemetry_topic + control_topic for char in "#+"):
        raise ConfigError("MQTT topics must not contain wildcards")

    temperature_min_c = _number(
        values["temperature_min_c"], "TEMPERATURE_MIN_C", minimum=-55.0, maximum=125.0
    )
    temperature_max_c = _number(
        values["temperature_max_c"], "TEMPERATURE_MAX_C", minimum=-55.0, maximum=125.0
    )
    if temperature_min_c > temperature_max_c:
        raise ConfigError("TEMPERATURE_MIN_C must not exceed TEMPERATURE_MAX_C")

    return Settings(
        mqtt_broker=broker,
        mqtt_port=port,
        mqtt_topic_sub=telemetry_topic,
        mqtt_topic_pub=control_topic,
        mqtt_client_id=_required_text(values["mqtt_client_id"], "MQTT_CLIENT_ID"),
        mqtt_user=str(values["mqtt_user"] or ""),
        mqtt_password=str(values["mqtt_password"] or ""),
        device_id=_required_text(values["device_id"], "DEVICE_ID"),
        flow_min_lpm=_number(values["flow_min_lpm"], "FLOW_MIN_LPM", minimum=0.000001),
        pressure_max_kpa=_number(values["pressure_max_kpa"], "PRESSURE_MAX_KPA", minimum=0.000001),
        temperature_min_c=temperature_min_c,
        temperature_max_c=temperature_max_c,
    )
