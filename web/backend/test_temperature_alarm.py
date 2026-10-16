from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from models import AlarmLog, Base
from temperature_alarm import TemperatureAlarmService, TemperatureThresholdError


def dt(second=0):
    return datetime(2026, 9, 20, 10, 0, second)


@pytest.fixture
def alarm_env():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    service = TemperatureAlarmService(factory, defaults=(0.0, 60.0))
    yield service, factory
    engine.dispose()


def test_thresholds_require_finite_ordered_ds18b20_range(alarm_env):
    service, _ = alarm_env
    for minimum, maximum in ((60.0, 60.0), (61.0, 60.0), (float("nan"), 60), (-56, 60), (0, 126)):
        with pytest.raises(TemperatureThresholdError):
            service.update_thresholds(minimum, maximum)
    assert service.update_thresholds(5.0, 60.0)["minimum_c"] == 5.0


def test_temp2_alarm_opens_once_and_clears_once(alarm_env):
    service, factory = alarm_env
    service.update_thresholds(5.0, 60.0)
    assert service.process_temp2("dev", 61.0, dt(0))["active"] is True
    assert service.process_temp2("dev", 62.0, dt(1)) is None
    cleared = service.process_temp2("dev", 60.0, dt(2))
    assert cleared["active"] is False
    assert service.process_temp2("dev", 59.0, dt(3)) is None
    with factory() as session:
        assert session.query(AlarmLog).count() == 1
        assert session.query(AlarmLog).one().cleared_at == dt(2)


def test_low_high_transition_clears_old_alarm_and_opens_new_one(alarm_env):
    service, factory = alarm_env
    service.update_thresholds(5.0, 60.0)
    service.process_temp2("dev", 4.0, dt(0))
    service.process_temp2("dev", 61.0, dt(1))
    with factory() as session:
        rows = session.query(AlarmLog).order_by(AlarmLog.id).all()
        assert [row.alarm_type for row in rows] == [
            "outlet_temperature_low",
            "outlet_temperature_high",
        ]
        assert rows[0].active is False
        assert rows[1].active is True


def test_missing_or_non_finite_temp2_is_ignored(alarm_env):
    service, factory = alarm_env
    assert service.process_temp2("dev", None, dt()) is None
    assert service.process_temp2("dev", float("nan"), dt()) is None
    with factory() as session:
        assert session.query(AlarmLog).count() == 0


def test_alarm_query_filters_time_and_returns_trigger_details(alarm_env):
    service, _ = alarm_env
    service.update_thresholds(5.0, 60.0)
    service.process_temp2("dev", 61.0, dt(1))
    service.process_temp2("dev", 50.0, dt(2))
    result = service.query_alarms(dt(0), dt(3), 50, 0)
    assert result["total"] == 1
    assert result["rows"][0]["value"] == 61.0
    assert result["rows"][0]["threshold"] == 60.0
    assert result["rows"][0]["status"] == "cleared"


def test_threshold_and_alarm_routes_use_stable_errors(alarm_env):
    service, factory = alarm_env
    with (
        patch.object(main, "SessionLocal", factory),
        patch.object(main, "temperature_alarm_service", service),
    ):
        client = TestClient(main.app)
        assert client.get("/api/v1/temperature-thresholds").json()["maximum_c"] == 60.0
        response = client.put(
            "/api/v1/temperature-thresholds",
            json={"minimum_c": 5.0, "maximum_c": 55.0},
        )
        assert response.status_code == 200
        assert response.json()["maximum_c"] == 55.0
        invalid = client.put(
            "/api/v1/temperature-thresholds",
            json={"minimum_c": 60.0, "maximum_c": 55.0},
        )
        assert invalid.status_code == 422
        assert invalid.json()["detail"]["code"] == "invalid_temperature_thresholds"
