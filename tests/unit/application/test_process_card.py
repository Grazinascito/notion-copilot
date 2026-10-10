"""Testes do ciclo do card: ⏳ → agente → validação → escrita → move (FR-005–FR-011)."""

from __future__ import annotations

from tests.unit.application.fakes import (
    FakeAgent,
    FakeClock,
    FakeReader,
    FakeWriter,
    golden_agent_json,
    make_card,
)

from notion_copilot.adapters.logging_fs import EventLog
from notion_copilot.application.process_card import process_card
from notion_copilot.domain.models import IAStatus

TEMPLATE = "T: {{TITULO}}\nP:\n{{PROPRIEDADES}}\nB: {{CORPO}}"


def invoke(tmp_path, *, agent_raw=None, card=None):
    journal: list = []
    card = card or make_card()
    deps = {
        "reader": FakeReader([card], markdown="corpo original", journal=journal),
        "writer": FakeWriter(journal=journal),
        "agent": FakeAgent(agent_raw or golden_agent_json(), journal=journal),
        "clock": FakeClock(),
        "events": EventLog(state_dir=tmp_path),
        "prompt_template": TEMPLATE,
    }
    result = process_card(card, run_id="r1", **deps)
    return result, deps, journal


def test_marks_the_card_running_before_invoking_the_agent(tmp_path):
    result, deps, journal = invoke(tmp_path)

    assert result.outcome == "success"
    statuses = [status for _, status, _ in deps["writer"].ia_status_calls]
    assert statuses[0] == IAStatus.RODANDO
    actions = [action for _, action, _ in journal]
    assert actions.index("set_ia_status") < actions.index("run_refine")


def test_delivers_title_properties_and_body_inside_the_prompt(tmp_path):
    result, deps, _ = invoke(tmp_path)

    assert result.outcome == "success"
    prompt = deps["agent"].prompts[0]
    assert "ligar pra estacio pra saber como pegar bolsa do curso" in prompt
    assert "Pipeline: To Refine" in prompt
    assert "corpo original" in prompt
    assert "{{" not in prompt


def test_treats_invalid_agent_json_as_a_permanent_error_with_no_retry(tmp_path):
    result, deps, _ = invoke(tmp_path, agent_raw="isto não é JSON")

    assert result.outcome == "error"
    assert result.error_kind == "agent_invalid_json"
    assert len(deps["agent"].prompts) == 1
    assert deps["writer"].moved == []
    last_status = deps["writer"].ia_status_calls[-1][1]
    assert last_status == IAStatus.ERRO


def test_writes_each_of_the_seven_sections_one_update_per_section(tmp_path):
    result, deps, _ = invoke(tmp_path)

    assert result.outcome == "success"
    assert len(deps["writer"].updates) == 1
    page_id, updates = deps["writer"].updates[0]
    assert page_id == "card-1"
    assert len(updates) == 7
    assert all(op.old_str.startswith("### ") for op in updates)


def test_rewrites_the_title_and_fills_executor_only_when_it_is_empty(tmp_path):
    result, deps, _ = invoke(tmp_path)
    assert result.outcome == "success"
    assert deps["writer"].titles == [
        ("card-1", "Ligar para a Estácio sobre bolsa do curso")
    ]
    assert deps["writer"].executors == [("card-1", "Humano")]

    result2, deps2, _ = invoke(tmp_path, card=make_card(executor="IA"))
    assert result2.outcome == "success"
    assert deps2["writer"].executors == []


def test_moves_the_card_to_refined_and_clears_ia_status_on_success(tmp_path):
    result, deps, _ = invoke(tmp_path)

    assert result.outcome == "success"
    assert deps["writer"].moved == ["card-1"]
    last_status = deps["writer"].ia_status_calls[-1][1]
    assert last_status is None


def test_ends_a_card_with_blocking_questions_in_precisa_de_voce(tmp_path):
    blocking = golden_agent_json(blocking=["Você já é aluno da Estácio? (sim / não)"])

    result, deps, _ = invoke(tmp_path, agent_raw=blocking)

    assert result.outcome == "needs_you"
    assert deps["writer"].moved == ["card-1"]
    last_status = deps["writer"].ia_status_calls[-1][1]
    assert last_status == IAStatus.PRECISA_DE_VOCE
