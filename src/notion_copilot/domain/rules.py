"""Regras do pipeline — a máquina de estados vive em código, nunca em prompt
(constituição I). Zero IO: recebem dados já buscados pelos adapters.
"""

from __future__ import annotations

from notion_copilot.domain.models import (
    REFINE_SECTION_KEYS,
    Card,
    MarkdownUpdate,
    Pipeline,
    RefineOutput,
)

# Headings do template do banco (research R1): a página nasce com eles e o
# orquestrador preenche os corpos. Chave = seção do contrato do agente.
SECTION_HEADINGS: dict[str, str] = {
    "contexto": "### Contexto",
    "links_guardados": "### Links guardados",
    "acoes_sugeridas": "### Ações sugeridas",
    "o_que_ja_adiantei": "### O que já adiantei",
    "perguntas_abertas": "### Perguntas abertas",
    "prompt_sugerido": "### Prompt sugerido",
    "executor_sugerido": "### Executor sugerido",
}


def is_eligible(card: Card) -> bool:
    """FR-004: somente raia To Refine com IA status vazio."""
    return card.pipeline == Pipeline.TO_REFINE and card.ia_status is None


def select_cards(cards: list[Card], limit: int) -> list[Card]:
    """FR-004: filtra elegíveis, ordena pelos mais antigos, limita a `limit`."""
    eligible = [card for card in cards if is_eligible(card)]
    eligible.sort(key=lambda card: card.created_at)
    return eligible[:limit]


def build_section_fill_ops(output: RefineOutput) -> list[MarkdownUpdate]:
    """Research R1: uma operação update_content por seção.

    old_str = heading do template (único na página); new_str = heading + corpo.
    O heading permanece a primeira linha do new_str — o template não é alterado.
    """
    return [
        MarkdownUpdate(
            old_str=SECTION_HEADINGS[key],
            new_str=f"{SECTION_HEADINGS[key]}\n{output.sections[key]}",
        )
        for key in REFINE_SECTION_KEYS
    ]


def render_properties(card: Card) -> str:
    """Propriedades do card para o prompt; '(vazio)' marca propriedade vazia."""
    return "\n".join(
        [
            f"Pipeline: {card.pipeline.value}",
            f"Executor: {card.executor.value if card.executor else '(vazio)'}",
            f"IA status: {card.ia_status.value if card.ia_status else '(vazio)'}",
            (
                "IA atualizado em: "
                + card.ia_updated_at.isoformat()
                if card.ia_updated_at
                else "IA atualizado em: (vazio)"
            ),
        ]
    )


def render_prompt(template: str, card: Card) -> str:
    """FR-007: entrega título, propriedades e corpo dentro do prompt versionado."""
    return (
        template.replace("{{TITULO}}", card.title)
        .replace("{{PROPRIEDADES}}", render_properties(card))
        .replace("{{CORPO}}", card.body_markdown)
    )
