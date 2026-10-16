import json
import math
import tempfile
import unittest
from pathlib import Path

from config import ConfigError, load_settings


class SettingsTest(unittest.TestCase):
    def test_missing_config_uses_safe_defaults(self):
        missing = Path(tempfile.gettempdir()) / "water-race-missing-config.json"
        settings = load_settings(environ={}, config_path=missing)

        self.assertEqual(settings.mqtt_broker, "192.0.2.10")
        self.assertEqual(settings.mqtt_port, 1883)
        self.assertEqual(settings.mqtt_user, "")
        self.assertEqual(settings.mqtt_password, "")
        self.assertEqual(settings.device_id, "watercycle-001")
        self.assertEqual(settings.flow_min_lpm, 0.50)
        self.assertEqual(settings.pressure_max_kpa, 500.0)
        self.assertEqual(settings.temperature_min_c, 0.0)
        self.assertEqual(settings.temperature_max_c, 60.0)

    def test_file_values_are_overridden_by_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps({"mqtt_port": 1884, "flow_min_lpm": 0.75}),
                encoding="utf-8",
            )
            settings = load_settings(
                environ={
                    "MQTT_PORT": "2883",
                    "FLOW_MIN_LPM": "1.25",
                    "TEMPERATURE_MIN_C": "5.0",
                },
                config_path=path,
            )

        self.assertEqual(settings.mqtt_port, 2883)
        self.assertEqual(settings.flow_min_lpm, 1.25)
        self.assertEqual(settings.temperature_min_c, 5.0)
        self.assertEqual(settings.public_dict()["thresholds"]["temperature_min"], 5.0)

    def test_invalid_values_are_rejected(self):
        cases = [
            ({"MQTT_PORT": "0"}, "MQTT_PORT"),
            ({"MQTT_PORT": "not-a-port"}, "MQTT_PORT"),
            ({"FLOW_MIN_LPM": "-0.1"}, "FLOW_MIN_LPM"),
            ({"FLOW_MIN_LPM": str(math.inf)}, "FLOW_MIN_LPM"),
            ({"PRESSURE_MAX_KPA": "0"}, "PRESSURE_MAX_KPA"),
            ({"TEMPERATURE_MIN_C": "-56"}, "TEMPERATURE_MIN_C"),
            ({"TEMPERATURE_MAX_C": "126"}, "TEMPERATURE_MAX_C"),
            ({"MQTT_BROKER": ""}, "MQTT_BROKER"),
        ]
        for environ, field in cases:
            with self.subTest(field=field, value=environ[field]):
                with self.assertRaisesRegex(ConfigError, field):
                    load_settings(environ=environ, config_path=Path("missing.json"))

    def test_temperature_minimum_cannot_exceed_maximum(self):
        with self.assertRaisesRegex(ConfigError, "TEMPERATURE_MIN_C"):
            load_settings(
                environ={"TEMPERATURE_MIN_C": "61", "TEMPERATURE_MAX_C": "60"},
                config_path=Path("missing.json"),
            )

    def test_unknown_file_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"mqtt_pasword": "typo"}', encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "mqtt_pasword"):
                load_settings(environ={}, config_path=path)


if __name__ == "__main__":
    unittest.main()
