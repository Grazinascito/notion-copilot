"""Comentários como membro do workspace (FR-014 emendado 2026-10-11): o corpo
do comentário traz o conteúdo relevante — perguntas bloqueantes ou saída do
erro — e nunca cita o `run_id`."""

from __future__ import annotations

import json
from datetime import datetime

from notion_copilot.domain.models import RefineOutput
from notion_copilot.domain.rules import (
    COMMENT_MAX_CHARS,
    build_error_comment,
    build_needs_you_comment,
    build_stale_comment,
)
from tests.unit.application.fakes import GOLDEN_AGENT_OUTPUT


def make_output(blocking: list[str]) -> RefineOutput:
    payload = json.loads(json.dumps(GOLDEN_AGENT_OUTPUT))
    payload["blocking_questions"] = blocking
    return RefineOutput.model_validate(payload)


def test_the_needs_you_comment_lists_each_blocking_question_on_its_own_line():
    output = make_output(["Qual método? (a / b)", "Prazo já venceu? (sim / não)"])

    text = build_needs_you_comment(output)

    assert "1. Qual método? (a / b)" in text
    assert "2. Prazo já venceu? (sim / não)" in text


def test_needs_you_comment_respects_the_comment_limit():
    long_questions = [f"Pergunta {n} " + "x" * 400 for n in range(1, 8)]

    text = build_needs_you_comment(make_output(long_questions))

    assert len(text) <= COMMENT_MAX_CHARS


def test_the_error_comment_includes_the_error_kind_and_the_error_output():
    text = build_error_comment(
        "agent_invalid_json", "Expecting value: line 1 column 1 (char 0)"
    )

    assert "agent_invalid_json" in text
    assert "Expecting value: line 1 column 1 (char 0)" in text


def test_the_error_comment_truncates_output_longer_than_the_comment_limit():
    text = build_error_comment("boom", "x" * 5000)

    assert len(text) <= COMMENT_MAX_CHARS
    assert "(truncado)" in text


def test_the_stale_comment_states_since_when_the_card_was_running_and_how_to_retry():
    text = build_stale_comment(datetime(2026, 10, 10, 10, 0))

    assert "10/10/2026" in text
    assert "10:00" in text
    assert "limpe o IA status" in text


def test_no_comment_text_cites_the_run_id():
    texts = [
        build_needs_you_comment(make_output(["Qual método? (a / b)"])),
        build_error_comment("agent_invalid_json", "erro"),
        build_stale_comment(datetime(2026, 10, 10, 10, 0)),
    ]

    for text in texts:
        assert "Execução" not in text
