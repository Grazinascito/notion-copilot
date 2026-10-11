"""Regras do pipeline — a máquina de estados vive em código, nunca em prompt
(constituição I). Zero IO: recebem dados já buscados pelos adapters.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime

from notion_copilot.domain.models import (
    REFINE_SECTION_KEYS,
    Card,
    IAStatus,
    MarkdownUpdate,
    Pipeline,
    RefineOutput,
)


class TemporaryFailure(Exception):
    """Falha de infraestrutura que pode passar sozinha (rede, 429/5xx do
    Notion). Traduzida pelo adapter; merece retry (FR-016, research R8).

    Tudo o que não é TemporaryFailure é tratado como permanente: timeout do
    agente (decisão 2026-10-10), JSON inválido, 4xx.
    """


def is_retryable(exc: Exception) -> bool:
    """R8: somente falhas de infraestrutura repetem."""
    return isinstance(exc, TemporaryFailure)


def is_stale(card: Card, *, now: datetime, stale_after_s: float) -> bool:
    """FR-017: card ⏳ cuja última transição de IA status passa do corte."""
    if card.ia_status is not IAStatus.RODANDO:
        return False
    if card.ia_updated_at is None:
        return False
    return (now - card.ia_updated_at).total_seconds() > stale_after_s


def with_retry[T](
    operation: Callable[[], T],
    *,
    backoff_s: list[int],
    sleep: Callable[[float], None],
) -> tuple[T, int]:
    """FR-016: executa a operação; TemporaryFailure espera e repete.

    Devolve (resultado, tentativas usadas) — no máximo 1 + len(backoff_s).
    A última tentativa propaga o erro para o chamador.
    """
    attempts = 1
    for delay in backoff_s:
        try:
            return operation(), attempts
        except TemporaryFailure:
            sleep(delay)
            attempts += 1
    return operation(), attempts

# Headings do template (research R1): páginas criadas a partir do template do
# banco nascem com eles. Quando a página não tem o esqueleto, o orquestrador
# o cria (ADR-008) — o agente nunca escreve headings.
SECTION_HEADINGS: dict[str, str] = {
    "contexto": "### Contexto",
    "links_guardados": "### Links guardados",
    "acoes_sugeridas": "### Ações sugeridas",
    "o_que_ja_adiantei": "### O que já adiantei",
    "perguntas_abertas": "### Perguntas abertas",
    "prompt_sugerido": "### Prompt sugerido",
    "executor_sugerido": "### Executor sugerido",
}

REFINEMENT_HEADING = "## 🔍 Refinamento"
ORIGINAL_RECORD_HEADING = "## 📝 Registro original"


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


def has_refinement_skeleton(markdown: str) -> bool:
    """ADR-008: a página tem o heading da seção de refinamento?"""
    return REFINEMENT_HEADING in markdown


def has_original_record(markdown: str) -> bool:
    """FR-015/R9: a página já tem o bloco 📝 Registro original?"""
    return ORIGINAL_RECORD_HEADING in markdown


def has_refinement(markdown: str) -> bool:
    """FR-015/R9: alguma seção do contrato já tem corpo entre seu heading e o
    heading seguinte? O heading sozinho (esqueleto) NÃO conta — a página é a
    verdade, não uma flag em propriedade.
    """
    for key in REFINE_SECTION_KEYS:
        heading = SECTION_HEADINGS[key]
        idx = markdown.find(heading)
        if idx == -1:
            continue
        after = markdown[idx + len(heading) :]
        next_heading = re.search(r"^#{1,6} ", after, re.M)
        body = after[: next_heading.start()] if next_heading else after
        if body.strip():
            return True
    return False


def extract_refinement_heading_line(markdown: str) -> str | None:
    """Linha completa do heading 🔍 (com a data) — old_str exato para inserir
    o bloco 📝 antes dela."""
    match = re.search(rf"^{re.escape(REFINEMENT_HEADING)}.*$", markdown, re.M)
    return match.group(0) if match else None


def build_original_record_block(title: str, body: str) -> str:
    """FR-006: bloco imutável com o texto exato da captura (título + corpo)."""
    block = f"{ORIGINAL_RECORD_HEADING}\n\n> {title}"
    if body.strip():
        block += f"\n\n{body}"
    return block


def capture_body_for_record(markdown: str) -> str:
    """Corpo da captura para o 📝: o markdown da página sem a seção de
    refinamento (em rodadas interrompidas, o esqueleto não é captura)."""
    return markdown.split(REFINEMENT_HEADING)[0].strip()


def build_refinement_insert(output: RefineOutput, now: datetime) -> str:
    """ADR-008: bloco markdown completo da seção, para páginas sem esqueleto.

    O heading com data e os 7 headings são criados pelo orquestrador (em
    código) — não dependem do template do banco nem do agente. Formato de data
    igual ao que o template do Notion renderiza (DD/MM/AAAA HH:MM).
    """
    lines = [f"{REFINEMENT_HEADING} — {now.strftime('%d/%m/%Y %H:%M')}"]
    for key in REFINE_SECTION_KEYS:
        lines.append(SECTION_HEADINGS[key])
        lines.append(output.sections[key])
    return "\n\n".join(lines)


# FR-014 (emendado 2026-10-11): a API do Notion aceita até 2000 caracteres por
# objeto rich_text; 1900 deixa folga para a menção e o espaço que o adapter
# acrescenta na frente.
COMMENT_MAX_CHARS = 1900

RETRY_HINT = (
    "Para tentar de novo, limpe o IA status do card — ele volta para a fila "
    "de refinamento."
)


def _fit(text: str) -> str:
    """Trunca para o limite do comentário, marcando o corte."""
    if len(text) <= COMMENT_MAX_CHARS:
        return text
    marker = "\n(truncado)"
    return text[: COMMENT_MAX_CHARS - len(marker)] + marker


def build_needs_you_comment(output: RefineOutput) -> str:
    """FR-014 no ❓: as perguntas bloqueantes vêm no corpo do comentário —
    a leitora responde sem abrir a página. Sem `run_id`: o rastro completo
    continua nos eventos JSON locais."""
    questions = "\n".join(
        f"{n}. {question}" for n, question in enumerate(output.blocking_questions, 1)
    )
    return _fit(
        "❓ Precisa de você: perguntas que bloqueiam o próximo passo."
        f"\n\n{questions}"
    )


def build_error_comment(error_kind: str, message: str) -> str:
    """FR-014 no ⚠️: a saída do erro (tipo + mensagem) vem no corpo do
    comentário."""
    return _fit(
        f"⚠️ Falha no processamento ({error_kind}).\n\n"
        f"Saída do erro:\n{message}\n\n"
        f"{RETRY_HINT}"
    )


def build_stale_comment(started_at: datetime | None) -> str:
    """FR-017 no ⚠️ abandonado: diz desde quando o card estava em ⏳ e como
    tentar de novo."""
    since = (
        f"desde {started_at.strftime('%d/%m/%Y %H:%M')} e passou de 30 minutos"
        if started_at
        else "há mais de 30 minutos"
    )
    return _fit(
        f"⚠️ Falha: este card ficou em ⏳ rodando {since}. "
        "O processo foi interrompido antes de terminar."
        f"\n\n{RETRY_HINT}"
    )


def render_properties(card: Card) -> str:
    """Propriedades do card para o prompt; '(vazio)' marca propriedade vazia.

    Prefere o mapa completo (todas as propriedades do card: Type, Area, Due
    Date, Details…); sem o mapa, renderiza os campos estruturados.
    """
    if card.properties:
        return "\n".join(
            f"{name}: {value if value else '(vazio)'}"
            for name, value in card.properties.items()
        )
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
