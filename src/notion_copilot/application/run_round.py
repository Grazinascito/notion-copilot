"""Rodada (FR-001 a FR-005): lock → pré-flight → seleção → loop de cards →
eventos. Processo de vida curta; a fila é a coluna To Refine (ADR-003).
"""

from __future__ import annotations

import time
from collections.abc import Callable

from notion_copilot.application.ports import (
    AgentRunner,
    Clock,
    EventSink,
    NotionReader,
    NotionWriter,
    RoundLock,
)
from notion_copilot.application.process_card import process_card
from notion_copilot.config import Settings
from notion_copilot.domain.models import Card, CardResult, IAStatus, new_run_id
from notion_copilot.domain.rules import (
    build_stale_comment,
    is_eligible,
    is_stale,
    select_cards,
    with_retry,
)

# Eventos de rodada usam stage "round": os estágios do data-model
# (preflight|select|refine|write|move|comment) descrevem etapas de card.
ROUND_STAGE = "round"


def run_round(
    *,
    settings: Settings,
    reader: NotionReader,
    writer: NotionWriter,
    agent: AgentRunner,
    clock: Clock,
    lock: RoundLock,
    events: EventSink,
    prompt_template: str,
    preflight: Callable[[], list[str]],
    single_card: str | None = None,
    dry_run: bool = False,
    sink: Callable[[str], None] = print,
) -> int:
    """Executa uma rodada e devolve o exit code (contracts/cli-commands.md)."""
    run_id = new_run_id(clock.now())

    # FR-003: rodada sobreposta termina na hora, sem custo de API
    if not lock.acquire():
        events.emit(run_id=run_id, stage=ROUND_STAGE, event="round_skipped_lock_busy")
        return 2
    try:
        problems = preflight()
        if problems:
            for problem in problems:
                sink(f"✘ {problem}")
            events.emit(
                run_id=run_id,
                stage=ROUND_STAGE,
                event="preflight_failed",
                detail={"problems": problems},
            )
            return 1
        events.emit(run_id=run_id, stage=ROUND_STAGE, event="round_started")

        if single_card is None:
            # FR-017/R7: varre ⏳ abandonados antes da seleção (modo --card
            # não varre — contracts/cli-commands.md)
            _sweep_stale(reader, writer, settings, run_id, events, clock)

        selected = _select(reader, settings, run_id, events, single_card, sink)
        if selected is None:
            return 1

        if dry_run:
            for card in selected:
                sink(f"· {card.title} ({card.page_id})")
            events.emit(
                run_id=run_id,
                stage=ROUND_STAGE,
                event="dry_run_finished",
                detail={"cards": [card.page_id for card in selected]},
            )
            return 0

        results: list[CardResult] = []
        for card in selected:
            result = process_card(
                card,
                run_id=run_id,
                reader=reader,
                writer=writer,
                agent=agent,
                clock=clock,
                events=events,
                prompt_template=prompt_template,
                notion_user_id=settings.notion_user_id,
                retry_backoff_s=settings.retry_backoff_s,
            )
            results.append(result)
            sink(f"· {card.page_id}: {result.outcome}")
        events.emit(run_id=run_id, stage=ROUND_STAGE, event="round_finished")
        # contracts/cli-commands.md: 3 = rodada com cards em erro
        if any(result.outcome == "error" for result in results):
            return 3
        return 0
    finally:
        lock.release()


def _sweep_stale(
    reader: NotionReader,
    writer: NotionWriter,
    settings: Settings,
    run_id: str,
    events: EventSink,
    clock: Clock,
) -> None:
    """FR-017: ⏳ abandonado (processo interrompido) vira ⚠️ com comentário."""
    candidates = reader.query_stale_running(settings.stale_after_s)
    for card in candidates:
        if is_stale(card, now=clock.now(), stale_after_s=settings.stale_after_s):
            _mark_stale_card(card, writer, settings, run_id, events, clock)


def _mark_stale_card(
    card: Card,
    writer: NotionWriter,
    settings: Settings,
    run_id: str,
    events: EventSink,
    clock: Clock,
) -> None:
    with_retry(
        lambda: writer.set_ia_status(card.page_id, IAStatus.ERRO, now=clock.now()),
        backoff_s=settings.retry_backoff_s,
        sleep=time.sleep,
    )
    events.emit(
        run_id=run_id,
        card_id=card.page_id,
        stage="refine",
        event="card_marked_stale",
    )
    try:
        with_retry(
            lambda: writer.add_comment(
                card.page_id,
                build_stale_comment(card.ia_updated_at),
                settings.notion_user_id,
            ),
            backoff_s=settings.retry_backoff_s,
            sleep=time.sleep,
        )
    except Exception:
        pass  # notificação falha silenciosa; o ⚠️ já está no board


def _select(
    reader: NotionReader,
    settings: Settings,
    run_id: str,
    events: EventSink,
    single_card: str | None,
    sink: Callable[[str], None],
) -> list[Card] | None:
    if single_card:
        card = reader.get_card(single_card)
        if not is_eligible(card):
            events.emit(
                run_id=run_id,
                card_id=card.page_id,
                stage="select",
                event="card_not_eligible",
            )
            sink(
                f"✘ card {single_card} inelegível: precisa estar em To Refine "
                "com IA status vazio (FR-004)"
            )
            return None
        return [card]

    candidates = reader.query_eligible(settings.max_cards_per_round)
    selected = select_cards(candidates, settings.max_cards_per_round)
    events.emit(
        run_id=run_id,
        stage="select",
        event="cards_selected",
        detail={"count": len(selected)},
    )
    return selected
