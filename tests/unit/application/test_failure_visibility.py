"""Testes da falha visível: ⚠️ isolado, retry, comentários, abandonados (US-3)."""

from __future__ import annotations

from datetime import datetime

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
from notion_copilot.application.process_card import process_card
from notion_copilot.application.run_round import run_round
from notion_copilot.config import Settings
from notion_copilot.domain.models import IAStatus, Pipeline

USER_ID = "user-123"
PROMPT_TEMPLATE = "T: {{TITULO}}\nP:\n{{PROPRIEDADES}}\nB: {{CORPO}}"


def invoke_card(tmp_path, *, agent=None, reader=None, writer=None, sleeps=None):
    card = make_card(page_id="card-1")
    sleeps = sleeps if sleeps is not None else []
    journal: list = []
    deps = {
        "reader": reader or FakeReader([card], journal=journal),
        "writer": writer or FakeWriter(journal=journal),
        "agent": agent or FakeAgent(golden_agent_json(), journal=journal),
        "clock": FakeClock(),
        "events": EventLog(state_dir=tmp_path),
        "prompt_template": PROMPT_TEMPLATE,
        "notion_user_id": USER_ID,
        "retry_backoff_s": [30, 120],
        "sleep": sleeps.append,
    }
    result = process_card(card, run_id="run-1", **deps)
    return result, deps


def invoke_round(tmp_path, cards, *, agent=None, stale_cards=None, overrides=None):
    journal: list = []
    deps = {
        "settings": Settings(
            _env_file=None, state_dir=tmp_path, notion_user_id=USER_ID
        ),
        "reader": FakeReader(
            cards, journal=journal, stale_cards=stale_cards, get_card_overrides=overrides
        ),
        "writer": FakeWriter(journal=journal),
        "agent": agent or FakeAgent(golden_agent_json(), journal=journal),
        "clock": FakeClock(),
        "lock": FakeLock(),
        "events": EventLog(state_dir=tmp_path),
        "prompt_template": PROMPT_TEMPLATE,
        "preflight": lambda: [],
    }
    code = run_round(**deps)
    return code, deps


def test_marks_the_card_error_after_two_retries_with_30s_and_120s_backoff(tmp_path):
    # duas primeiras leituras da página falham com 429 (temporário); a terceira
    # passa — sem retry o card viraria ⚠️ na primeira falha (FR-016)
    card = make_card(page_id="card-1")
    journal: list = []
    reader = FakeReader([card], journal=journal, flaky_markdown_reads=2)
    sleeps: list[float] = []

    result, deps = invoke_card(tmp_path, reader=reader, sleeps=sleeps)

    assert result.outcome == "success"
    assert result.attempts == 3
    assert sleeps == [30.0, 120.0]


def test_marks_only_the_failing_card_and_continues_the_round(tmp_path):
    def raw_for(card_id: str) -> str:
        return "json inválido" if card_id == "bad" else golden_agent_json()

    cards = [
        make_card(page_id="bad", created_at=datetime(2026, 10, 11, 10, 0)),
        make_card(page_id="good", created_at=datetime(2026, 10, 11, 11, 0)),
    ]
    agent = FakeAgent(raw_for)

    code, deps = invoke_round(tmp_path, cards, agent=agent)
    writer = deps["writer"]

    assert code == 3
    assert writer.moved == ["good"]
    statuses = {pid: status for pid, status, _ in writer.ia_status_calls}
    assert statuses["bad"] == IAStatus.ERRO
    assert statuses["good"] is None


def test_ends_a_card_with_blocking_questions_asking_them_in_the_comment(
    tmp_path,
):
    blocking = golden_agent_json(blocking=["Qual método? (a / b)"])

    result, deps = invoke_card(tmp_path, agent=FakeAgent(blocking))

    assert result.outcome == "needs_you"
    assert len(deps["writer"].comments) == 1
    page_id, text, mention = deps["writer"].comments[0]
    assert page_id == "card-1"
    assert mention == USER_ID
    assert "1. Qual método? (a / b)" in text
    assert "run-1" not in text  # FR-014 emendado: sem ponteiro de log


def test_leaves_a_comment_with_the_error_output_when_the_card_errors(tmp_path):
    result, deps = invoke_card(tmp_path, agent=FakeAgent("json inválido"))

    assert result.outcome == "error"
    assert len(deps["writer"].comments) == 1
    _, text, mention = deps["writer"].comments[0]
    assert mention == USER_ID
    assert "agent_invalid_json" in text
    assert "Saída do erro:" in text
    assert "run-1" not in text


def test_marks_a_stale_running_card_error_with_comment_before_selecting(tmp_path):
    stale = make_card(
        page_id="abandoned",
        ia_status=IAStatus.RODANDO,
        ia_updated_at=datetime(2026, 10, 10, 10, 0),  # 2h antes do FakeClock
    )
    fresh = make_card(page_id="new", created_at=datetime(2026, 10, 10, 11, 30))

    code, deps = invoke_round(tmp_path, [fresh], stale_cards=[stale])
    writer = deps["writer"]

    assert code == 0
    assert writer.moved == ["new"]
    statuses = {pid: status for pid, status, _ in writer.ia_status_calls}
    assert statuses["abandoned"] == IAStatus.ERRO
    stale_comments = [c for c in writer.comments if c[0] == "abandoned"]
    assert len(stale_comments) == 1
    assert stale_comments[0][2] == USER_ID
    assert "10/10/2026" in stale_comments[0][1]  # desde quando estava em ⏳
    content = (deps["events"]._events_path).read_text()
    assert "card_marked_stale" in content


def test_writes_nothing_and_logs_card_moved_during_processing(tmp_path):
    card = make_card(page_id="card-1")
    moved_away = card.model_copy(update={"pipeline": Pipeline.REFINED})
    journal: list = []
    reader = FakeReader(
        [card], journal=journal, get_card_overrides={"card-1": moved_away}
    )

    result, deps = invoke_card(tmp_path, reader=reader)
    writer = deps["writer"]

    assert result.outcome == "skipped_moved"
    assert writer.moved == []
    assert writer.updates == []
    assert writer.appends == []
    assert writer.titles == []
    statuses = [status for _, status, _ in writer.ia_status_calls]
    assert statuses[-1] is None  # card volta a status vazio, sem efeitos
    content = (deps["events"]._events_path).read_text()
    assert "card_moved_during_processing" in content


def test_ends_the_round_with_exit_code_3_when_at_least_one_card_errored(tmp_path):
    code, _ = invoke_round(tmp_path, [make_card()], agent=FakeAgent("json inválido"))

    assert code == 3
