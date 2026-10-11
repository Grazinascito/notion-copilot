"""Testes dos marcadores de idempotência por card (FR-015, R9)."""

from notion_copilot.domain.rules import (
    build_original_record_block,
    extract_refinement_heading_line,
    has_original_record,
    has_refinement,
)

EMPTY_SKELETON = "\n".join(
    [
        "## 🔍 Refinamento — 10/10/2026 11:00",
        "### Contexto",
        "### Links guardados",
        "### Ações sugeridas",
        "### O que já adiantei",
        "### Perguntas abertas",
        "### Prompt sugerido",
        "### Executor sugerido",
    ]
)


def test_detects_the_registro_original_block():
    with_record = "## 📝 Registro original\n\n> captura original"
    without_record = EMPTY_SKELETON

    assert has_original_record(with_record) is True
    assert has_original_record(without_record) is False


def test_detects_a_filled_section_body_between_a_template_heading_and_the_next_heading():
    filled = EMPTY_SKELETON.replace(
        "### Contexto\n", "### Contexto\n\n**Síntese.** Trabalho já feito.\n"
    )

    assert has_refinement(EMPTY_SKELETON) is False
    assert has_refinement(filled) is True


def test_does_not_treat_the_template_skeleton_alone_as_a_refinement():
    # o esqueleto (headings sem corpo) é o estado de card recém-criado, não de
    # card refinado — o heading sozinho nunca conta (R9)
    assert has_refinement(EMPTY_SKELETON) is False


def test_extracts_the_full_refinement_heading_line_including_the_date():
    markdown = f"texto\n\n{EMPTY_SKELETON}\n"

    line = extract_refinement_heading_line(markdown)

    assert line == "## 🔍 Refinamento — 10/10/2026 11:00"


def test_builds_the_original_record_block_with_exact_capture_text():
    block = build_original_record_block("captura original", "detalhe do corpo")

    assert block.startswith("## 📝 Registro original")
    assert "> captura original" in block
    assert "detalhe do corpo" in block

    empty_body = build_original_record_block("só o título", "")
    assert "só o título" in empty_body
    assert empty_body.endswith("só o título")
