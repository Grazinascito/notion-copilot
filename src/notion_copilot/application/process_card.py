"""Ciclo de um card (FR-005 a FR-012): ⏳ → registro → agente → validar →
escrever → mover. Um evento JSON por etapa; toda escrita é do orquestrador
(FR-009) — o agente nunca recebe ferramenta de Notion (FR-008).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import ValidationError

from notion_copilot.application.ports import (
    AgentRunner,
    Clock,
    EventSink,
    NotionReader,
    NotionWriter,
)
from notion_copilot.domain.models import (
    Card,
    CardOutcome,
    CardResult,
    Executor,
    IAStatus,
    MarkdownUpdate,
    RefineOutput,
)
from notion_copilot.domain.rules import (
    build_original_record_block,
    build_refinement_insert,
    build_section_fill_ops,
    capture_body_for_record,
    extract_refinement_heading_line,
    has_original_record,
    has_refinement,
    has_refinement_skeleton,
    render_prompt,
)


def process_card(
    card: Card,
    *,
    run_id: str,
    reader: NotionReader,
    writer: NotionWriter,
    agent: AgentRunner,
    clock: Clock,
    events: EventSink,
    prompt_template: str,
) -> CardResult:
    started = clock.now()
    try:
        return _cycle(
            card,
            run_id=run_id,
            reader=reader,
            writer=writer,
            agent=agent,
            clock=clock,
            events=events,
            prompt_template=prompt_template,
            started=started,
        )
    except ValidationError as exc:
        return _fail(card, run_id, writer, clock, events, started, "agent_invalid_json", exc)
    except ValueError as exc:
        return _fail(card, run_id, writer, clock, events, started, "agent_invalid_output", exc)
    except TimeoutError as exc:
        return _fail(card, run_id, writer, clock, events, started, "agent_timeout", exc)
    except Exception as exc:  # US-3 refina a classificação por tipo
        return _fail(card, run_id, writer, clock, events, started, type(exc).__name__, exc)


def _cycle(
    card: Card,
    *,
    run_id: str,
    reader: NotionReader,
    writer: NotionWriter,
    agent: AgentRunner,
    clock: Clock,
    events: EventSink,
    prompt_template: str,
    started: datetime,
) -> CardResult:
    # FR-005: ⏳ antes de qualquer chamada ao agente
    writer.set_ia_status(card.page_id, IAStatus.RODANDO, now=clock.now())
    events.emit(run_id=run_id, card_id=card.page_id, stage="refine", event="card_marked_running")

    # FR-007: todo o conteúdo do card vai no prompt (o agente não lê o Notion)
    markdown = reader.get_page_markdown(card.page_id)

    # FR-015/R9: card já refinado reprocessado por engano — nenhuma escrita de
    # conteúdo; desfecho skipped_already_refined (move + limpa status)
    if has_refinement(markdown):
        writer.move_to_refined(card.page_id)
        writer.set_ia_status(card.page_id, None, now=clock.now())
        events.emit(
            run_id=run_id,
            card_id=card.page_id,
            stage="write",
            event="card_skipped_already_refined",
        )
        return CardResult(
            card_id=card.page_id,
            outcome="skipped_already_refined",
            attempts=1,
            duration_s=(clock.now() - started).total_seconds(),
        )

    full_card = card.model_copy(update={"body_markdown": markdown})
    prompt = render_prompt(prompt_template, full_card)
    raw = agent.run_refine(prompt, run_id, card.page_id)
    events.emit(run_id=run_id, card_id=card.page_id, stage="refine", event="agent_finished")

    # Pydantic na fronteira: JSON fora do contrato é erro permanente (R8)
    output = RefineOutput.model_validate_json(raw)

    # FR-009/FR-010: o orquestrador grava as 7 seções. FR-006: o 📝 Registro
    # original — texto exato da captura — vem ANTES de qualquer reescrita, nos
    # dois caminhos: página com esqueleto → update_content (R1); sem esqueleto
    # → o orquestrador cria a seção completa (ADR-008).
    record = None
    if not has_original_record(markdown):
        record = build_original_record_block(
            card.title, capture_body_for_record(markdown)
        )

    if has_refinement_skeleton(markdown):
        updates: list[MarkdownUpdate] = build_section_fill_ops(output)
        heading_line = extract_refinement_heading_line(markdown)
        if record is not None and heading_line is not None:
            updates.insert(
                0,
                MarkdownUpdate(
                    old_str=heading_line, new_str=f"{record}\n\n{heading_line}"
                ),
            )
        writer.apply_markdown_updates(card.page_id, updates)
    else:
        block = f"{record}\n\n{build_refinement_insert(output, now=clock.now())}" if record else build_refinement_insert(output, now=clock.now())
        writer.append_markdown(card.page_id, block)
    events.emit(run_id=run_id, card_id=card.page_id, stage="write", event="sections_written")

    writer.set_title(card.page_id, output.title)
    if card.executor is None:
        # Contrato do agente é "HUMANO"|"IA"; o board usa "Humano"|"IA"
        writer.set_executor(card.page_id, Executor[output.executor_suggestion].value)

    # FR-011/FR-012: Refined; o código decide o estado final a partir da lista (R11)
    writer.move_to_refined(card.page_id)
    events.emit(run_id=run_id, card_id=card.page_id, stage="move", event="card_moved_to_refined")

    outcome: CardOutcome
    if output.blocking_questions:
        writer.set_ia_status(card.page_id, IAStatus.PRECISA_DE_VOCE, now=clock.now())
        outcome = "needs_you"
    else:
        writer.set_ia_status(card.page_id, None, now=clock.now())
        outcome = "success"
    return CardResult(
        card_id=card.page_id,
        outcome=outcome,
        attempts=1,
        duration_s=(clock.now() - started).total_seconds(),
    )


def _fail(
    card: Card,
    run_id: str,
    writer: NotionWriter,
    clock: Clock,
    events: EventSink,
    started: datetime,
    error_kind: str,
    exc: Exception,
) -> CardResult:
    """FR-013 (parcial): somente este card vira ⚠️; a rodada continua."""
    writer.set_ia_status(card.page_id, IAStatus.ERRO, now=clock.now())
    events.emit(
        run_id=run_id,
        card_id=card.page_id,
        stage="refine",
        event="card_error",
        detail={"error_kind": error_kind, "message": str(exc)[:200]},
    )
    return CardResult(
        card_id=card.page_id,
        outcome="error",
        error_kind=error_kind,
        attempts=1,
        duration_s=(clock.now() - started).total_seconds(),
    )
