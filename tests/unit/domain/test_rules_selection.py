"""Testes da seleção da fila (FR-004/FR-005)."""

from datetime import datetime, timedelta

from notion_copilot.domain.models import IAStatus, Pipeline
from notion_copilot.domain.rules import select_cards
from tests.unit.application.fakes import make_card

BASE = datetime(2026, 10, 10, 11, 0)


def test_selects_only_cards_in_to_refine_with_empty_ia_status():
    eligible = make_card(page_id="a", created_at=BASE)
    refined = make_card(
        page_id="b", pipeline=Pipeline.REFINED, created_at=BASE + timedelta(minutes=1)
    )

    selected = select_cards([refined, eligible], limit=5)

    assert [c.page_id for c in selected] == ["a"]


def test_orders_selected_cards_oldest_first_and_limits_to_5():
    cards = [
        make_card(page_id=f"c{i}", created_at=BASE + timedelta(minutes=i))
        for i in range(7)
    ]

    selected = select_cards(list(reversed(cards)), limit=5)

    assert [c.page_id for c in selected] == ["c0", "c1", "c2", "c3", "c4"]


def test_never_selects_a_card_with_running_needs_you_or_error_status():
    running = make_card(page_id="run", ia_status=IAStatus.RODANDO)
    needs = make_card(page_id="needs", ia_status=IAStatus.PRECISA_DE_VOCE)
    error = make_card(page_id="err", ia_status=IAStatus.ERRO)

    selected = select_cards([running, needs, error], limit=5)

    assert selected == []
