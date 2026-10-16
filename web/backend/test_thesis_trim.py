from fastapi.testclient import TestClient

import main


def test_retired_competition_and_workbench_routes_are_absent():
    client = TestClient(main.app)
    assert client.post("/api/v1/judge", json={}).status_code == 404
    assert client.post("/api/v1/analysis").status_code == 404
    assert client.get("/api/v1/analyses").status_code == 404
    assert client.get("/api/v1/tests/active").status_code == 404
    assert client.get("/api/v1/tests").status_code == 404
    assert client.get("/api/v1/test-samples").status_code == 404


def test_core_monitoring_control_and_alarm_routes_remain():
    paths = {route.path for route in main.app.routes}
    assert {
        "/health",
        "/api/v1/status",
        "/api/v1/telemetry",
        "/api/v1/control",
        "/api/v1/controls",
        "/api/v1/alarms",
        "/api/v1/temperature-thresholds",
    } <= paths


def test_status_has_no_judge_analysis_or_water_level_configuration():
    response = TestClient(main.app).get("/api/v1/status")
    assert response.status_code == 200
    payload = response.json()
    assert "water_level" not in payload
    assert "judge_configured" not in payload["config"]
    assert "analysis_configured" not in payload["config"]
    assert "water_level" not in payload["config"]["thresholds"]
    assert payload["config"]["thresholds"]["flow_min_for_heating"] == 0.5


def test_existing_control_ack_is_persisted_as_accepted():
    from datetime import datetime
    import json
    from types import SimpleNamespace
    from unittest.mock import patch

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from models import Base, ControlLog

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        session.add(
            ControlLog(
                command_id="cmd-ack-1",
                timestamp=datetime.now(),
                expire_after=30,
                cmd="{}",
                status="pending",
            )
        )
        session.commit()

    message = SimpleNamespace(
        payload=json.dumps({"ack": {"command_id": "cmd-ack-1", "status": "accept"}}).encode()
    )
    with patch.object(main, "SessionLocal", session_factory), patch.object(
        main, "scan_expired_commands"
    ):
        main.on_message(None, None, message)

    with session_factory() as session:
        assert session.query(ControlLog).one().status == "accepted"
    engine.dispose()


def test_frontend_only_exposes_thesis_core_features():
    from pathlib import Path

    html = (Path(__file__).resolve().parent.parent / "static" / "index.html").read_text(
        encoding="utf-8"
    )
    for retired in (
        "btn_test_start",
        "btn_sample_query",
        "btn_judge_manual",
        "btn_analysis",
        "water_level",
        "/api/v1/tests",
        "/api/v1/test-samples",
        "/api/v1/judge",
        "/api/v1/analysis",
    ):
        assert retired not in html
    for retained in (
        'id="temp1"',
        'id="temp2"',
        'id="pressure"',
        'id="flow"',
        'id="btn_pump_on"',
        'id="btn_heat_on"',
        'id="alarm_list"',
    ):
        assert retained in html
