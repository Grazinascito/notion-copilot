"""Rodada (FR-001 a FR-005): lock → pré-flight → seleção → loop de cards →
eventos. Processo de vida curta; a fila é a coluna To Refine (ADR-003).
"""

from __future__ import annotations

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
from notion_copilot.domain.models import Card, new_run_id
from notion_copilot.domain.rules import is_eligible, select_cards

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
            )
            sink(f"· {card.page_id}: {result.outcome}")
        events.emit(run_id=run_id, stage=ROUND_STAGE, event="round_finished")
        return 0
    finally:
        lock.release()


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
