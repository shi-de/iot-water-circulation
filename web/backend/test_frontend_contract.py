import unittest
from pathlib import Path


STATIC = Path(__file__).resolve().parent.parent / "static"


class FrontendContractTest(unittest.TestCase):
    def test_frontend_has_core_status_controls_alarms_and_history(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        logic = (STATIC / "frontend_logic.js").read_text(encoding="utf-8")

        for element_id in (
            "mqtt_state", "device_age", "temp1", "temp2", "pressure", "flow",
            "btn_pump_on", "btn_heat_on", "alarm_list", "control_list", "myChart",
        ):
            with self.subTest(element_id=element_id):
                self.assertIn(f'id="{element_id}"', html)
        self.assertIn("MQTT未连接，暂不能控制设备", logic)
        self.assertIn("设备数据已过期，暂不能控制设备", logic)
        self.assertIn("setInterval(pollStatus, 500)", html)
        self.assertIn("/api/v1/telemetry", html)
        self.assertIn("/api/v1/temperature-thresholds", html)

    def test_removed_competition_demo_and_workbench_features_are_absent(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        logic = (STATIC / "frontend_logic.js").read_text(encoding="utf-8")

        for retired in (
            "btn_test_start", "btn_sample_query", "/api/v1/tests",
            "/api/v1/test-samples", "btn_judge_manual", "/api/v1/judge",
            "btn_analysis", "/api/v1/analysis", "water_level",
        ):
            with self.subTest(retired=retired):
                self.assertNotIn(retired, html)
                self.assertNotIn(retired, logic)

    def test_command_ack_and_alarm_edge_handling_remain(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        logic = (STATIC / "frontend_logic.js").read_text(encoding="utf-8")

        self.assertIn("等待设备ACK", html)
        self.assertIn('"accepted"', html)
        self.assertIn("new WaterRaceUI.AlarmEdgeTracker()", html)
        self.assertIn("cache: \"no-store\"", html)
        self.assertIn("lastChartTimestamp", html)


if __name__ == "__main__":
    unittest.main()
