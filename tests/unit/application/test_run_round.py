"""Testes da rodada: lock, pré-flight, seleção, loop de cards (FR-001–FR-004)."""

from __future__ import annotations

from pathlib import Path

from tests.unit.application.fakes import (
    FakeAgent,
    FakeClock,
    FakeLock,
    FakeReader,
    FakeWriter,
    golden_agent_json,
    make_card,
)

from notion_copilot.adapters.logging_fs import EventLog
from notion_copilot.application.run_round import run_round
from notion_copilot.config import Settings
from notion_copilot.domain.models import IAStatus

PROMPT_TEMPLATE = "T: {{TITULO}}\nP:\n{{PROPRIEDADES}}\nB: {{CORPO}}"


def invoke(cards, tmp_path, *, lock_busy=False, preflight=None, **overrides):
    journal: list = []
    deps = {
        "settings": Settings(_env_file=None, state_dir=Path("/tmp/nc-test-state")),
        "reader": FakeReader(cards, journal=journal),
        "writer": FakeWriter(journal=journal),
        "agent": FakeAgent(golden_agent_json(), journal=journal),
        "clock": FakeClock(),
        "lock": FakeLock(busy=lock_busy),
        "events": EventLog(state_dir=tmp_path),
        "prompt_template": PROMPT_TEMPLATE,
        "preflight": preflight if preflight is not None else (lambda: []),
    }
    deps.update(overrides)
    code = run_round(**deps)
    return code, deps


def test_acquires_the_lock_runs_preflight_selects_and_processes_each_card_then_releases(
    tmp_path,
):
    code, deps = invoke([make_card(page_id="a"), make_card(page_id="b")], tmp_path)

    assert code == 0
    assert deps["lock"].acquired is True
    assert deps["lock"].released is True
    assert deps["writer"].moved == ["a", "b"]
    assert deps["agent"].prompts != []


def test_stops_with_exit_code_2_when_the_lock_is_already_held_without_querying_cards(
    tmp_path,
):
    code, deps = invoke([make_card()], tmp_path, lock_busy=True)

    assert code == 2
    assert deps["reader"].query_calls == 0


def test_ends_an_empty_queue_round_after_a_single_query_writing_nothing(tmp_path):
    code, deps = invoke([], tmp_path)

    assert code == 0
    assert deps["reader"].query_calls == 1
    assert deps["writer"].moved == []
    assert deps["agent"].prompts == []


def test_dry_run_lists_what_it_would_do_without_writing_anything(tmp_path):
    lines: list[str] = []

    code, deps = invoke(
        [make_card(page_id="a", title="titulo do card")],
        tmp_path,
        dry_run=True,
        sink=lines.append,
    )

    assert code == 0
    assert deps["agent"].prompts == []
    assert deps["writer"].moved == []
    assert any("titulo do card" in line for line in lines)


def test_processes_only_the_given_card_in_card_mode(tmp_path):
    code, deps = invoke(
        [make_card(page_id="a"), make_card(page_id="b")], tmp_path, single_card="b"
    )

    assert code == 0
    assert deps["reader"].query_calls == 0
    assert deps["writer"].moved == ["b"]


def test_refuses_an_ineligible_card_with_card_not_eligible(tmp_path):
    code, deps = invoke(
        [make_card(page_id="a", ia_status=IAStatus.RODANDO)], tmp_path, single_card="a"
    )

    assert code == 1
    assert deps["writer"].moved == []
    assert deps["agent"].prompts == []
    content = (tmp_path / "logs" / "events.jsonl").read_text()
    assert "card_not_eligible" in content


def test_stops_with_exit_code_1_when_preflight_reports_problems(tmp_path):
    code, deps = invoke(
        [make_card()],
        tmp_path,
        preflight=lambda: ["NOTION_TOKEN ausente no .env"],
    )

    assert code == 1
    assert deps["reader"].query_calls == 0
