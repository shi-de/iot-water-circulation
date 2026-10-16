import unittest
from types import SimpleNamespace

import main
from main import MQTT_PASS, MQTT_USER, create_mqtt_client


class FakeMqttClient:
    def __init__(self, client_id):
        self.client_id = client_id
        self.username = None
        self.password = None
        self.min_delay = None
        self.max_delay = None

    def username_pw_set(self, username, password):
        self.username = username
        self.password = password

    def reconnect_delay_set(self, min_delay, max_delay):
        self.min_delay = min_delay
        self.max_delay = max_delay


class FakeLifecycleClient:
    def __init__(self):
        self.calls = []

    def connect_async(self, host, port, keepalive):
        self.calls.append(("connect_async", host, port, keepalive))

    def loop_start(self):
        self.calls.append(("loop_start",))


class FakeSubscribeClient:
    def __init__(self, subscribe_rc=0):
        self.subscribe_rc = subscribe_rc
        self.subscriptions = []

    def subscribe(self, topic):
        self.subscriptions.append(topic)
        return self.subscribe_rc, 17


class MqttClientConfigTest(unittest.TestCase):
    def test_backend_mqtt_credentials_come_from_runtime_settings(self):
        self.assertEqual(MQTT_USER, main.SETTINGS.mqtt_user)
        self.assertEqual(MQTT_PASS, main.SETTINGS.mqtt_password)

    def test_client_is_configured_with_credentials_and_reconnect_delay(self):
        client = create_mqtt_client(client_factory=FakeMqttClient)

        if MQTT_USER or MQTT_PASS:
            self.assertEqual(client.username, MQTT_USER)
            self.assertEqual(client.password, MQTT_PASS)
        else:
            self.assertIsNone(client.username)
            self.assertIsNone(client.password)
        self.assertEqual(client.min_delay, 1)
        self.assertEqual(client.max_delay, 10)

    def test_start_uses_async_connect_so_initial_broker_outage_can_recover(self):
        client = FakeLifecycleClient()

        main.start_mqtt_client(client)

        self.assertEqual(
            client.calls,
            [
                ("connect_async", main.MQTT_BROKER, main.MQTT_PORT, 60),
                ("loop_start",),
            ],
        )

    def test_callbacks_record_return_codes_and_last_packet_time(self):
        client = FakeSubscribeClient()
        main.g_mqtt_last_message_at = "2026-09-19T15:03:56.993248"

        main.on_connect(client, None, {}, 0)
        main.on_disconnect(client, None, 7)

        self.assertEqual(client.subscriptions, [main.MQTT_TOPIC_SUB])
        self.assertEqual(main.g_mqtt_last_connect_rc, 0)
        self.assertEqual(main.g_mqtt_last_disconnect_rc, 7)
        self.assertEqual(main.g_mqtt_last_message_at, "2026-09-19T15:03:56.993248")

    def test_last_packet_time_updates_even_when_payload_is_invalid(self):
        main.g_mqtt_last_message_at = None

        main.on_message(None, None, SimpleNamespace(payload=b"not-json", topic="testtopic/1"))

        self.assertIsNotNone(main.g_mqtt_last_message_at)


if __name__ == "__main__":
    unittest.main()
