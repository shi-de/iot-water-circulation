import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from models import AlarmLog, Base, Telemetry


class FakePublishClient:
    def __init__(self, connected=True, rc=0):
        self.connected = connected
        self.rc = rc
        self.published = []

    def is_connected(self):
        return self.connected

    def publish(self, topic, payload):
        self.published.append((topic, payload))
        return SimpleNamespace(rc=self.rc)


class MainBehaviorTest(unittest.TestCase):
    def test_control_publish_rejects_when_mqtt_is_disconnected(self):
        client = FakePublishClient(connected=False)
        with patch.object(main, "mqtt_client", client):
            with self.assertRaises(HTTPException) as raised:
                main.publish_control_payload("{}")

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(client.published, [])

    def test_alarm_faults_keep_trigger_value_and_threshold(self):
        faults = main.build_alarm_faults(
            flow=0.2,
            pressure=650.0,
            temp1=61.0,
            alarm_code=0,
        )

        self.assertEqual(
            faults,
            [
                ("水流量过低", 0.2, 0.5),
                ("水压力超限", 650.0, 500.0),
                ("进水温度超上限", 61.0, 60.0),
            ],
        )

    def test_alarm_threshold_boundaries_match_firmware_interlock(self):
        self.assertEqual(
            main.build_alarm_faults(flow=0.50, pressure=499.99, temp1=60.0, temp2=60.0),
            [],
        )
        self.assertEqual(
            main.build_alarm_faults(flow=0.49, pressure=500.0, temp1=60.01),
            [
                ("水流量过低", 0.49, 0.5),
                ("水压力超限", 500.0, 500.0),
                ("进水温度超上限", 60.01, 60.0),
            ],
        )

    def test_temperature_minimum_boundary_is_inclusive(self):
        self.assertEqual(main.build_alarm_faults(temp1=0.0, temp2=0.0), [])
        self.assertEqual(
            main.build_alarm_faults(temp1=-0.01),
            [("进水温度超下限", -0.01, 0.0)],
        )

    def test_status_exposes_public_thresholds_and_units_without_password(self):
        response = TestClient(main.app).get("/api/v1/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["config"]["thresholds"]["flow_min_for_heating"], 0.50)
        self.assertEqual(payload["config"]["units"]["flow"], "L/min")
        serialized = json.dumps(payload).lower()
        self.assertNotIn("mqtt_password", serialized)
        self.assertNotIn("mqtt_pass", serialized)


class TelemetryContractTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        self.previous_state = main.g_latest_device
        main.g_latest_device = {
            **self.previous_state,
            "temp1": None,
            "temp2": None,
            "temperature": None,
            "mode": "manual",
            "raw": {},
        }

    def tearDown(self):
        main.g_latest_device = self.previous_state
        self.engine.dispose()

    def send_payload(self, payload):
        message = SimpleNamespace(payload=json.dumps(payload).encode("utf-8"))
        with (
            patch.object(main, "SessionLocal", self.session_factory),
            patch.object(main, "scan_expired_commands"),
        ):
            main.on_message(None, None, message)

        response = TestClient(main.app).get("/api/v1/status")
        self.assertEqual(response.status_code, 200)
        with self.session_factory() as session:
            telemetry = session.query(Telemetry).one()
            alarm_count = session.query(AlarmLog).count()
        return response.json(), telemetry, alarm_count

    def test_current_firmware_payload_is_normalized_in_status_and_sqlite(self):
        payload = {
            "device": "esp-manual-test",
            "temp1": 24.75,
            "temp2": 26.5,
            "temperature": 26.5,
            "pressure": 32.7,
            "flow": 21.87,
            "pump": 1,
            "heater": 1,
            "alarm": 0,
            "mode": "auto",
        }

        status, telemetry, alarm_count = self.send_payload(payload)

        expected = {
            "device_id": "esp-manual-test",
            "temp1": 24.75,
            "temp2": 26.5,
            "temperature": 26.5,
            "pressure": 32.7,
            "flow": 21.87,
            "pump_state": 1,
            "heat_state": 1,
            "alarm": 0,
            "mode": "auto",
            "fault_text": "",
        }
        for key, value in expected.items():
            self.assertEqual(status[key], value, key)
            self.assertEqual(getattr(telemetry, key), value, key)
        self.assertEqual(status["raw"], payload)
        self.assertEqual(json.loads(telemetry.raw_json), payload)
        self.assertEqual(alarm_count, 0)

    def test_canonical_payload_remains_canonical(self):
        payload = {
            "device_id": "water-cycle-02",
            "seq": 17,
            "temp1": 25.0,
            "temp2": 26.0,
            "temperature": 25.5,
            "pressure": 40.0,
            "flow": 8.5,
            "pump_state": 1,
            "heat_state": 0,
            "alarm": 0,
            "mode": "manual",
        }

        status, telemetry, alarm_count = self.send_payload(payload)

        for key in (
            "device_id",
            "seq",
            "temp1",
            "temp2",
            "temperature",
            "pressure",
            "flow",
            "pump_state",
            "heat_state",
            "alarm",
            "mode",
        ):
            self.assertEqual(status[key], payload[key], key)
            self.assertEqual(getattr(telemetry, key), payload[key], key)
        self.assertEqual(alarm_count, 0)

    def test_invalid_temperatures_keep_previous_valid_values_and_raw_payload(self):
        main.g_latest_device = {
            **main.g_latest_device,
            "temp1": 23.5,
            "temp2": 24.5,
            "temperature": 24.0,
        }
        payload = {
            "device": "esp-manual-test",
            "temp1": -99.0,
            "temp2": 200.0,
            "temperature": -99.0,
            "pressure": 32.7,
            "flow": 21.87,
            "pump": 0,
            "heater": 0,
            "alarm": 1,
            "mode": "manual",
        }

        status, telemetry, alarm_count = self.send_payload(payload)

        self.assertEqual(status["temp1"], 23.5)
        self.assertEqual(status["temp2"], 24.5)
        self.assertEqual(status["temperature"], 24.5)
        self.assertEqual(telemetry.temp1, 23.5)
        self.assertEqual(telemetry.temp2, 24.5)
        self.assertEqual(telemetry.temperature, 24.5)
        self.assertEqual(status["raw"], payload)
        self.assertEqual(json.loads(telemetry.raw_json), payload)
        self.assertEqual(alarm_count, 1)


if __name__ == "__main__":
    unittest.main()
