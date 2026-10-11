"""Testes do log de eventos JSON e do rastro do agente (RNF-O1/O2/O3/O5)."""

import json

from notion_copilot.adapters.logging_fs import EventLog


def read_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_writes_one_json_line_per_event_with_the_required_fields(tmp_path):
    log = EventLog(state_dir=tmp_path)

    log.emit(run_id="r1", stage="select", event="round_started")
    log.emit(
        run_id="r1",
        card_id="card-1",
        stage="refine",
        event="agent_finished",
        duration_s=12.5,
        detail={"model": "glm-5.3"},
    )

    events = read_lines(tmp_path / "logs" / "events.jsonl")
    assert len(events) == 2

    first, second = events
    assert first["run_id"] == "r1"
    assert first["stage"] == "select"
    assert first["event"] == "round_started"
    assert "card_id" not in first

    assert second["card_id"] == "card-1"
    assert second["duration_s"] == 12.5
    assert second["detail"] == {"model": "glm-5.3"}
    for event in events:
        assert {"ts", "run_id", "stage", "event"} <= set(event)


def test_saves_the_agent_stream_json_trail_under_the_state_dir_named_by_run_id(
    tmp_path,
):
    log = EventLog(state_dir=tmp_path)

    trail_path = log.save_agent_trail(
        run_id="20261010T1425-7f3a", card_id="card-1", raw='{"type":"stream"}'
    )

    assert trail_path.is_file()
    assert "20261010T1425-7f3a" in str(trail_path)
    assert trail_path.read_text() == '{"type":"stream"}'


def test_never_writes_configured_secrets_into_events_or_trails(tmp_path):
    log = EventLog(state_dir=tmp_path)

    log.emit(
        run_id="r1",
        stage="preflight",
        event="checked_env",
        detail={"auth_token": "SECRET-VALUE", "notion_token": "SECRET-VALUE"},
    )

    content = (tmp_path / "logs" / "events.jsonl").read_text()
    assert "SECRET-VALUE" not in content
    assert "auth_token" not in content
    assert "notion_token" not in content
