"""Local MQTT interruption/recovery probe; no external broker is required."""

import argparse
import json
import socket
import threading
import time

import paho.mqtt.client as mqtt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from models import Base, Telemetry


def _read_exact(connection, size):
    data = b""
    while len(data) < size:
        chunk = connection.recv(size - len(data))
        if not chunk:
            raise ConnectionError("peer closed")
        data += chunk
    return data


def _read_packet(connection):
    header = _read_exact(connection, 1)[0]
    multiplier = 1
    remaining = 0
    while True:
        encoded = _read_exact(connection, 1)[0]
        remaining += (encoded & 0x7F) * multiplier
        if encoded & 0x80 == 0:
            break
        multiplier *= 128
    return header, _read_exact(connection, remaining)


def _encode_length(value):
    encoded = bytearray()
    while True:
        byte = value % 128
        value //= 128
        if value:
            byte |= 0x80
        encoded.append(byte)
        if not value:
            return bytes(encoded)


class MiniBroker:
    def __init__(self, port):
        self.port = port
        self.listener = None
        self.connections = set()
        self.lock = threading.Lock()
        self.running = threading.Event()
        self.subscribed = threading.Event()

    def start(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", self.port))
        listener.listen()
        listener.settimeout(0.2)
        self.listener = listener
        self.running.set()
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self):
        while self.running.is_set():
            try:
                connection, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with self.lock:
                self.connections.add(connection)
            threading.Thread(target=self._client_loop, args=(connection,), daemon=True).start()

    def _client_loop(self, connection):
        try:
            while self.running.is_set():
                header, body = _read_packet(connection)
                packet_type = header >> 4
                if packet_type == 1:
                    connection.sendall(b"\x20\x02\x00\x00")
                elif packet_type == 8:
                    packet_id = body[:2]
                    connection.sendall(b"\x90\x03" + packet_id + b"\x00")
                    self.subscribed.set()
                elif packet_type == 12:
                    connection.sendall(b"\xd0\x00")
                elif packet_type == 14:
                    return
        except (ConnectionError, OSError):
            pass
        finally:
            with self.lock:
                self.connections.discard(connection)
            try:
                connection.close()
            except OSError:
                pass

    def publish(self, topic, payload):
        topic_bytes = topic.encode("utf-8")
        payload_bytes = payload.encode("utf-8")
        body = len(topic_bytes).to_bytes(2, "big") + topic_bytes + payload_bytes
        packet = b"\x30" + _encode_length(len(body)) + body
        with self.lock:
            targets = list(self.connections)
        for connection in targets:
            try:
                connection.sendall(packet)
            except OSError:
                pass

    def stop(self):
        self.running.clear()
        if self.listener is not None:
            self.listener.close()
        with self.lock:
            targets = list(self.connections)
            self.connections.clear()
        for connection in targets:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()


def _wait_until(predicate, timeout, description):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise TimeoutError(description)


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def run(duration_seconds):
    port = _free_port()
    main.MQTT_BROKER = "127.0.0.1"
    main.MQTT_PORT = port
    main.MQTT_TOPIC_SUB = "watercycle/device/telemetry"
    main.g_mqtt_connected = False
    main.g_mqtt_connect_count = 0
    main.g_mqtt_last_message_at = None

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    main.SessionLocal = sessionmaker(bind=engine)

    received = []
    client = main.create_mqtt_client(client_factory=mqtt.Client)
    client.on_connect = main.on_connect
    client.on_disconnect = main.on_disconnect

    def on_message(mqtt_client, userdata, message):
        main.on_message(mqtt_client, userdata, message)
        received.append(time.monotonic())

    client.on_message = on_message
    broker = MiniBroker(port)
    main.start_mqtt_client(client)
    try:
        time.sleep(2)
        if main.g_mqtt_connected:
            raise AssertionError("client connected before the broker started")
        broker.start()
        _wait_until(lambda: broker.subscribed.is_set(), 15, "initial subscribe timed out")
        broker.publish(main.MQTT_TOPIC_SUB, json.dumps({"device_id": "probe", "seq": 0}))
        _wait_until(lambda: len(received) == 1, 5, "initial telemetry timed out")

        broker.stop()
        _wait_until(lambda: not main.g_mqtt_connected, 5, "disconnect callback timed out")
        time.sleep(2)

        broker = MiniBroker(port)
        broker.start()
        _wait_until(
            lambda: main.g_mqtt_connect_count >= 2 and broker.subscribed.is_set(),
            20,
            "reconnect/resubscribe timed out",
        )
        print(
            f"RECOVERED connect_count={main.g_mqtt_connect_count} "
            f"disconnect_rc={main.g_mqtt_last_disconnect_rc}",
            flush=True,
        )
        main.logger.setLevel("WARNING")

        started = time.monotonic()
        sequence = 1
        next_report = 60
        while time.monotonic() - started < duration_seconds:
            broker.publish(
                main.MQTT_TOPIC_SUB,
                json.dumps({"device_id": "probe", "seq": sequence}),
            )
            sequence += 1
            time.sleep(1)
            elapsed = int(time.monotonic() - started)
            if elapsed >= next_report:
                print(f"OBSERVED elapsed={elapsed}s received={len(received) - 1}", flush=True)
                next_report += 60

        post_recovery = received[1:]
        if len(post_recovery) < max(1, duration_seconds - 2):
            raise AssertionError(
                f"telemetry gap: received {len(post_recovery)} in {duration_seconds}s"
            )
        max_gap = max(
            (right - left for left, right in zip(post_recovery, post_recovery[1:])),
            default=0.0,
        )
        if max_gap > 2.5:
            raise AssertionError(f"post-recovery max telemetry gap was {max_gap:.3f}s")
        with main.SessionLocal() as session:
            persisted_sequences = [
                row[0]
                for row in session.query(Telemetry.seq)
                .filter(Telemetry.device_id == "probe")
                .order_by(Telemetry.seq)
                .all()
            ]
        if persisted_sequences != list(range(sequence)):
            raise AssertionError(
                f"persisted sequences differ: count={len(persisted_sequences)} "
                f"expected={sequence}"
            )
        print(
            f"PASS duration={duration_seconds}s received={len(post_recovery)} "
            f"persisted={len(persisted_sequences)} "
            f"max_gap={max_gap:.3f}s last_packet={main.g_mqtt_last_message_at}",
            flush=True,
        )
    finally:
        client.disconnect()
        client.loop_stop()
        broker.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=600)
    run(parser.parse_args().duration)
