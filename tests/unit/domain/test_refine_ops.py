"""Testes da construção de operações update_content (research R1) e do prompt."""

from datetime import datetime

from notion_copilot.domain.models import REFINE_SECTION_KEYS, RefineOutput
from notion_copilot.domain.rules import (
    SECTION_HEADINGS,
    build_refinement_insert,
    build_section_fill_ops,
    has_refinement_skeleton,
    render_prompt,
)
from tests.unit.application.fakes import GOLDEN_AGENT_OUTPUT, make_card


def test_builds_one_fill_operation_per_section_with_template_heading_as_old_str():
    output = RefineOutput.model_validate(GOLDEN_AGENT_OUTPUT)

    ops = build_section_fill_ops(output)

    assert len(ops) == 7
    assert [op.old_str for op in ops] == [
        SECTION_HEADINGS[key] for key in REFINE_SECTION_KEYS
    ]
    for op, key in zip(ops, REFINE_SECTION_KEYS, strict=True):
        body = output.sections[key]
        assert op.new_str == f"{SECTION_HEADINGS[key]}\n{body}"


def test_keeps_the_template_heading_unchanged_as_the_first_line_of_each_new_str():
    output = RefineOutput.model_validate(GOLDEN_AGENT_OUTPUT)

    ops = build_section_fill_ops(output)

    for op in ops:
        assert op.new_str.splitlines()[0] == op.old_str


def test_detects_whether_the_page_has_the_refinement_skeleton():
    with_skeleton = "texto da captura\n## 🔍 Refinamento — 10/10/2026\n### Contexto\n"
    without_skeleton = "só a frase da captura, sem nada"

    assert has_refinement_skeleton(with_skeleton) is True
    assert has_refinement_skeleton(without_skeleton) is False


def test_builds_the_full_refinement_block_with_heading_date_and_seven_sections():
    output = RefineOutput.model_validate(GOLDEN_AGENT_OUTPUT)

    block = build_refinement_insert(output, now=datetime(2026, 10, 10, 12, 0))

    lines = block.splitlines()
    assert lines[0] == "## 🔍 Refinamento — 10/10/2026 12:00"
    headings = [line for line in lines if line.startswith("### ")]
    assert headings == [SECTION_HEADINGS[key] for key in REFINE_SECTION_KEYS]
    for key in REFINE_SECTION_KEYS:
        assert output.sections[key] in block


def test_render_prompt_delivers_title_properties_and_body_in_the_placeholders():
    template = (
        "# Etapa\n\n## Card\n\nTítulo: {{TITULO}}\n\nPropriedades:\n"
        "{{PROPRIEDADES}}\n\nCorpo:\n{{CORPO}}\n"
    )
    card = make_card(title="titulo da captura")
    card = card.model_copy(update={"body_markdown": "corpo com detalhes"})

    prompt = render_prompt(template, card)

    assert "titulo da captura" in prompt
    assert "Pipeline: TO REFINE" in prompt
    assert "Executor: (vazio)" in prompt
    assert "corpo com detalhes" in prompt
    assert "{{" not in prompt


def test_the_versioned_prompt_template_contains_the_three_placeholders():
    import pathlib

    template = (pathlib.Path(__file__).parents[3] / "prompts" / "refine.md").read_text(
        encoding="utf-8"
    )

    for placeholder in ("{{TITULO}}", "{{PROPRIEDADES}}", "{{CORPO}}"):
        assert placeholder in template
