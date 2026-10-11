"""Testes do registro original e da idempotência no ciclo do card (FR-006/FR-015, R9)."""

from __future__ import annotations

from tests.unit.application.fakes import (
    SKELETON_MARKDOWN,
    FakeAgent,
    FakeClock,
    FakeReader,
    FakeWriter,
    golden_agent_json,
    make_card,
)

from notion_copilot.adapters.logging_fs import EventLog
from notion_copilot.application.process_card import process_card

TEMPLATE = "T: {{TITULO}}\nP:\n{{PROPRIEDADES}}\nB: {{CORPO}}"
RECORD_HEADING = "## 📝 Registro original"
REFINEMENT_HEADING = "## 🔍 Refinamento"


def invoke(tmp_path, *, markdown, card=None):
    journal: list = []
    card = card or make_card(title="captura original da grazi")
    deps = {
        "reader": FakeReader([card], markdown=markdown, journal=journal),
        "writer": FakeWriter(journal=journal),
        "agent": FakeAgent(golden_agent_json(), journal=journal),
        "clock": FakeClock(),
        "events": EventLog(state_dir=tmp_path),
        "prompt_template": TEMPLATE,
    }
    result = process_card(
        card,
        run_id="r1",
        notion_user_id="user-1",
        retry_backoff_s=[0, 0],
        sleep=lambda seconds: None,
        **deps,
    )
    return result, deps, journal


def test_creates_the_record_block_before_any_title_rewrite_and_before_the_section(
    tmp_path,
):
    result, deps, journal = invoke(tmp_path, markdown="")

    assert result.outcome == "success"
    page_id, block = deps["writer"].appends[0]
    record_pos = block.index(RECORD_HEADING)
    title_pos = block.index("> captura original da grazi")
    refinement_pos = block.index(REFINEMENT_HEADING)
    assert record_pos < title_pos < refinement_pos

    actions = [action for _, action, _ in journal]
    assert actions.index("append_markdown") < actions.index("set_title")


def test_does_not_create_a_second_record_block_when_the_marker_is_present(tmp_path):
    markdown = f"{RECORD_HEADING}\n\n> captura antiga\n\n{SKELETON_MARKDOWN}"

    result, deps, _ = invoke(tmp_path, markdown=markdown)

    assert result.outcome == "success"
    assert deps["writer"].appends == []
    page_id, updates = deps["writer"].updates[0]
    assert len(updates) == 7
    assert all(RECORD_HEADING not in op.new_str for op in updates)


def test_ends_an_already_refined_card_as_skipped_already_refined(tmp_path):
    filled = SKELETON_MARKDOWN.replace(
        "### Contexto\n", "### Contexto\n\n**Síntese.** Já refinado antes.\n"
    )

    result, deps, _ = invoke(tmp_path, markdown=filled)

    assert result.outcome == "skipped_already_refined"
    assert deps["agent"].prompts == []
    assert deps["writer"].updates == []
    assert deps["writer"].appends == []
    assert deps["writer"].titles == []
    assert deps["writer"].moved == ["card-1"]
    last_status = deps["writer"].ia_status_calls[-1][1]
    assert last_status is None


def test_fills_the_sections_while_preserving_an_existing_record_from_an_interrupted_run(
    tmp_path,
):
    # cenário R9: rodada morreu depois de gravar o 📝, antes de preencher
    markdown = f"{RECORD_HEADING}\n\n> captura da rodada anterior\n\n{SKELETON_MARKDOWN}"

    result, deps, _ = invoke(tmp_path, markdown=markdown)

    assert result.outcome == "success"
    assert deps["writer"].appends == []
    _, updates = deps["writer"].updates[0]
    assert len(updates) == 7
