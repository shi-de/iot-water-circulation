import unittest

from payload_adapter import normalize_device_payload


class NormalizeDevicePayloadTest(unittest.TestCase):
    def test_normalizes_current_esp_payload_for_frontend(self):
        state = normalize_device_payload(
            {
                "device": "esp-manual-test",
                "temperature": 25.63,
                "pressure": 32.70,
                "flow": 21.87,
                "pump": 1,
                "heater": 1,
                "alarm": 0,
            },
            previous_mode="manual",
        )

        self.assertEqual(state["device_id"], "esp-manual-test")
        self.assertEqual(state["temp1"], 25.63)
        self.assertEqual(state["temp2"], 25.63)
        self.assertEqual(state["pressure"], 32.70)
        self.assertEqual(state["flow"], 21.87)
        self.assertEqual(state["pump_state"], 1)
        self.assertEqual(state["heat_state"], 1)
        self.assertEqual(state["alarm"], 0)
        self.assertEqual(state["fault_text"], "")
        self.assertTrue(state["online"])

    def test_filters_invalid_temperature_and_keeps_previous_valid_value(self):
        state = normalize_device_payload(
            {
                "device": "esp-manual-test",
                "temp1": -99.0,
                "temp2": 28.25,
                "temperature": 28.25,
                "pressure": 32.70,
                "flow": 6.0,
                "pump": 1,
                "heater": 0,
                "alarm": 0,
            },
            previous_mode="manual",
            previous_state={"temp1": 26.50, "temp2": 28.00, "temperature": 28.00},
        )

        self.assertEqual(state["temp1"], 26.50)
        self.assertEqual(state["temp2"], 28.25)
        self.assertEqual(state["temperature"], 28.25)

    def test_does_not_expose_invalid_temperature_without_previous_value(self):
        state = normalize_device_payload(
            {"temp1": -99.0, "temp2": -99.0, "temperature": -99.0},
            previous_mode="manual",
        )

        self.assertIsNone(state["temp1"])
        self.assertIsNone(state["temp2"])
        self.assertIsNone(state["temperature"])


if __name__ == "__main__":
    unittest.main()
