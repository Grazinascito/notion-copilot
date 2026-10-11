"""Testes do contrato de saída do agente e das entidades (data-model.md)."""

import re
from datetime import datetime

import pytest
from pydantic import ValidationError

from notion_copilot.domain.models import (
    REFINE_SECTION_KEYS,
    CardResult,
    RefineOutput,
    new_run_id,
)

# Exemplo-ouro do contrato specs/001-refine-happy-path/contracts/agent-output.md
GOLDEN_EXAMPLE = {
    "title": "Ligar para a Estácio sobre bolsa do curso",
    "sections": {
        "contexto": "**Síntese.** ...\n- **Fato:** ... Fonte: [link]\n- **Hipótese:** ...",
        "links_guardados": "- [Nome](url) — por que importa",
        "acoes_sugeridas": "- [ ] ...",
        "o_que_ja_adiantei": "...",
        "perguntas_abertas": "...",
        "prompt_sugerido": "...",
        "executor_sugerido": "Humano — ...",
    },
    "blocking_questions": [],
    "executor_suggestion": "HUMANO",
}


def a_valid_refine_output() -> dict:
    import copy

    return copy.deepcopy(GOLDEN_EXAMPLE)


def test_accepts_the_golden_example_from_contracts_agent_output_md():
    output = RefineOutput.model_validate(a_valid_refine_output())

    assert output.title == "Ligar para a Estácio sobre bolsa do curso"
    assert set(output.sections) == set(REFINE_SECTION_KEYS)
    assert output.blocking_questions == []
    assert output.executor_suggestion == "HUMANO"


def test_rejects_a_title_longer_than_80_characters():
    payload = a_valid_refine_output()
    payload["title"] = "x" * 81

    with pytest.raises(ValidationError):
        RefineOutput.model_validate(payload)


def test_rejects_output_missing_any_of_the_seven_section_keys():
    for missing_key in REFINE_SECTION_KEYS:
        payload = a_valid_refine_output()
        del payload["sections"][missing_key]

        with pytest.raises(ValidationError):
            RefineOutput.model_validate(payload)


def test_rejects_executor_suggestion_outside_humano_and_ia():
    payload = a_valid_refine_output()
    payload["executor_suggestion"] = "Humano"

    with pytest.raises(ValidationError):
        RefineOutput.model_validate(payload)


def test_rejects_card_result_attempts_outside_1_and_3():
    def make(attempts: int) -> CardResult:
        return CardResult(
            card_id="page-1", outcome="success", attempts=attempts, duration_s=1.0
        )

    with pytest.raises(ValidationError):
        make(0)
    with pytest.raises(ValidationError):
        make(4)
    assert make(1).attempts == 1
    assert make(3).attempts == 3


def test_formats_run_id_as_yyyymmddthhmm_xxxx():
    run_id = new_run_id(datetime(2026, 10, 10, 14, 25))

    assert re.fullmatch(r"20261010T1425-[0-9a-f]{4}", run_id)
