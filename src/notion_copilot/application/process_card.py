"""Ciclo de um card (FR-005 a FR-018): ⏳ → registro → agente → validar →
escrever → mover. Um evento JSON por etapa; toda escrita é do orquestrador
(FR-009) — o agente nunca recebe ferramenta de Notion (FR-008).

Falha visível (US-3): erro isolado por card (FR-013), retry para falhas
temporárias (FR-016), comentário com menção e run_id em ⚠️/❓ (FR-014), e o
card nunca termina a rodada em ⏳ (FR-018).
"""

from __future__ import annotations

import time
from collections.abc import Callable
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
    Pipeline,
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
    with_retry,
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
    notion_user_id: str,
    retry_backoff_s: list[int],
    sleep: Callable[[float], None] = time.sleep,
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
            notion_user_id=notion_user_id,
            retry_backoff_s=retry_backoff_s,
            sleep=sleep,
            started=started,
        )
    except ValidationError as exc:
        return _fail(card, run_id, writer, clock, events, started, "agent_invalid_json", exc, notion_user_id, retry_backoff_s, sleep)
    except ValueError as exc:
        return _fail(card, run_id, writer, clock, events, started, "agent_invalid_output", exc, notion_user_id, retry_backoff_s, sleep)
    except TimeoutError as exc:
        return _fail(card, run_id, writer, clock, events, started, "agent_timeout", exc, notion_user_id, retry_backoff_s, sleep)
    except Exception as exc:  # demais erros são permanentes (R8)
        return _fail(card, run_id, writer, clock, events, started, type(exc).__name__, exc, notion_user_id, retry_backoff_s, sleep)


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
    notion_user_id: str,
    retry_backoff_s: list[int],
    sleep: Callable[[float], None],
    started: datetime,
) -> CardResult:
    # FR-005: ⏳ antes de qualquer chamada ao agente
    with_retry(
        lambda: writer.set_ia_status(card.page_id, IAStatus.RODANDO, now=clock.now()),
        backoff_s=retry_backoff_s,
        sleep=sleep,
    )
    events.emit(run_id=run_id, card_id=card.page_id, stage="refine", event="card_marked_running")

    def read_markdown() -> str:
        return reader.get_page_markdown(card.page_id)

    markdown, attempts = with_retry(
        read_markdown, backoff_s=retry_backoff_s, sleep=sleep
    )

    # FR-015/R9: card já refinado reprocessado por engano — nenhuma escrita de
    # conteúdo; desfecho skipped_already_refined (move + limpa status)
    if has_refinement(markdown):
        with_retry(
            lambda: writer.move_to_refined(card.page_id),
            backoff_s=retry_backoff_s,
            sleep=sleep,
        )
        with_retry(
            lambda: writer.set_ia_status(card.page_id, None, now=clock.now()),
            backoff_s=retry_backoff_s,
            sleep=sleep,
        )
        events.emit(
            run_id=run_id,
            card_id=card.page_id,
            stage="write",
            event="card_skipped_already_refined",
        )
        return CardResult(
            card_id=card.page_id,
            outcome="skipped_already_refined",
            attempts=attempts,
            duration_s=(clock.now() - started).total_seconds(),
        )

    # FR-007: todo o conteúdo do card vai no prompt (o agente não lê o Notion)
    full_card = card.model_copy(update={"body_markdown": markdown})
    prompt = render_prompt(prompt_template, full_card)
    raw = agent.run_refine(prompt, run_id, card.page_id)
    events.emit(run_id=run_id, card_id=card.page_id, stage="refine", event="agent_finished")

    # Pydantic na fronteira: JSON fora do contrato é erro permanente (R8)
    output = RefineOutput.model_validate_json(raw)

    # R10: card movido pela usuária durante o processamento — nada é gravado
    fresh, attempts_made = with_retry(
        lambda: reader.get_card(card.page_id), backoff_s=retry_backoff_s, sleep=sleep
    )
    attempts = max(attempts, attempts_made)
    if fresh.pipeline != Pipeline.TO_REFINE:
        with_retry(
            lambda: writer.set_ia_status(card.page_id, None, now=clock.now()),
            backoff_s=retry_backoff_s,
            sleep=sleep,
        )
        events.emit(
            run_id=run_id,
            card_id=card.page_id,
            stage="write",
            event="card_moved_during_processing",
        )
        return CardResult(
            card_id=card.page_id,
            outcome="skipped_moved",
            attempts=attempts,
            duration_s=(clock.now() - started).total_seconds(),
        )

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
        section_updates = list(updates)
        _, attempts_made = with_retry(
            lambda: writer.apply_markdown_updates(card.page_id, section_updates),
            backoff_s=retry_backoff_s,
            sleep=sleep,
        )
        attempts = max(attempts, attempts_made)
    else:
        refinement = build_refinement_insert(output, now=clock.now())
        block = f"{record}\n\n{refinement}" if record else refinement
        _, attempts_made = with_retry(
            lambda: writer.append_markdown(card.page_id, block),
            backoff_s=retry_backoff_s,
            sleep=sleep,
        )
        attempts = max(attempts, attempts_made)
    events.emit(run_id=run_id, card_id=card.page_id, stage="write", event="sections_written")

    new_title = output.title
    executor_value = Executor[output.executor_suggestion].value
    with_retry(
        lambda: writer.set_title(card.page_id, new_title),
        backoff_s=retry_backoff_s,
        sleep=sleep,
    )
    if card.executor is None:
        with_retry(
            lambda: writer.set_executor(card.page_id, executor_value),
            backoff_s=retry_backoff_s,
            sleep=sleep,
        )

    # FR-011/FR-012: Refined; o código decide o estado final a partir da lista (R11)
    with_retry(
        lambda: writer.move_to_refined(card.page_id),
        backoff_s=retry_backoff_s,
        sleep=sleep,
    )
    events.emit(run_id=run_id, card_id=card.page_id, stage="move", event="card_moved_to_refined")

    outcome: CardOutcome
    if output.blocking_questions:
        final_status = IAStatus.PRECISA_DE_VOCE
        outcome = "needs_you"
    else:
        final_status = None
        outcome = "success"
    with_retry(
        lambda: writer.set_ia_status(card.page_id, final_status, now=clock.now()),
        backoff_s=retry_backoff_s,
        sleep=sleep,
    )
    if output.blocking_questions:
        _comment(
            card.page_id,
            run_id,
            writer,
            events,
            notion_user_id,
            retry_backoff_s,
            sleep,
            "❓ Precisa de você: há pergunta(s) bloqueante(s) na seção "
            "'Perguntas abertas' da página. Execução ",
        )
    return CardResult(
        card_id=card.page_id,
        outcome=outcome,
        attempts=attempts,
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
    notion_user_id: str,
    retry_backoff_s: list[int],
    sleep: Callable[[float], None],
) -> CardResult:
    """FR-013: somente este card vira ⚠️ (permanece em To Refine, excluído da
    seleção até limpeza manual); FR-014: comentário com menção e run_id."""
    with_retry(
        lambda: writer.set_ia_status(card.page_id, IAStatus.ERRO, now=clock.now()),
        backoff_s=retry_backoff_s,
        sleep=sleep,
    )
    events.emit(
        run_id=run_id,
        card_id=card.page_id,
        stage="refine",
        event="card_error",
        detail={"error_kind": error_kind, "message": str(exc)[:200]},
    )
    _comment(
        card.page_id,
        run_id,
        writer,
        events,
        notion_user_id,
        retry_backoff_s,
        sleep,
        f"⚠️ Falha no processamento ({error_kind}): {str(exc)[:150]}. Execução ",
    )
    return CardResult(
        card_id=card.page_id,
        outcome="error",
        error_kind=error_kind,
        attempts=1,
        duration_s=(clock.now() - started).total_seconds(),
    )


def _comment(
    page_id: str,
    run_id: str,
    writer: NotionWriter,
    events: EventSink,
    notion_user_id: str,
    retry_backoff_s: list[int],
    sleep: Callable[[float], None],
    message_prefix: str,
) -> None:
    """FR-014/R6: comentário com menção (notificação) e run_id (RNF-O4)."""
    text = f"{message_prefix}{run_id}."
    try:
        with_retry(
            lambda: writer.add_comment(page_id, text, notion_user_id),
            backoff_s=retry_backoff_s,
            sleep=sleep,
        )
        events.emit(run_id=run_id, card_id=page_id, stage="comment", event="comment_posted")
    except Exception as exc:
        # comentário é o canal de notificação, não o trabalho em si: falha
        # aqui não derruba o desfecho do card — o board já mostra o estado
        events.emit(
            run_id=run_id,
            card_id=page_id,
            stage="comment",
            event="comment_failed",
            detail={"message": str(exc)[:200]},
        )
