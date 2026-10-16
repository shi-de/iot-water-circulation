import sqlite3
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models import AlarmLog, Base, ControlLog, Telemetry, TemperatureThreshold


class CoreModelSchemaTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_metadata_contains_only_runtime_core_tables(self):
        self.assertEqual(
            set(inspect(self.engine).get_table_names()),
            {"telemetry", "control_log", "alarm_log", "temperature_threshold"},
        )
        self.assertFalse(hasattr(Telemetry, "water_level"))
        self.assertFalse(hasattr(Telemetry, "judge_result"))

    def test_core_telemetry_control_and_alarm_models_remain_usable(self):
        self.session.add(Telemetry(device_id="d1", flow=1.5))
        self.session.add(ControlLog(command_id="c1", cmd='{"pump":1}'))
        self.session.add(AlarmLog(device_id="d1", alarm_type="flow", msg="低流量"))
        self.session.add(TemperatureThreshold(id=1, minimum_c=0.0, maximum_c=60.0))
        self.session.commit()
        self.assertEqual(self.session.query(Telemetry).one().flow, 1.5)
        self.assertEqual(self.session.query(ControlLog).one().status, "pending")
        self.assertEqual(self.session.query(AlarmLog).one().msg, "低流量")

    def test_initializing_core_metadata_does_not_drop_legacy_data_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "water.db"
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE test_run (task_number TEXT)")
            connection.execute("CREATE TABLE test_sample (value REAL)")
            connection.execute("INSERT INTO test_run VALUES ('legacy-1')")
            connection.execute("INSERT INTO test_sample VALUES (12.5)")
            connection.commit()
            connection.close()

            engine = create_engine(f"sqlite:///{path}")
            Base.metadata.create_all(engine)
            engine.dispose()

            connection = sqlite3.connect(path)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM test_run").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM test_sample").fetchone()[0], 1)
            connection.close()


if __name__ == "__main__":
    unittest.main()
