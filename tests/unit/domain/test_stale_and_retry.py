"""Testes da regra dos 30 min e da classificação de erros (FR-016/FR-017, R8)."""

from datetime import UTC, datetime, timedelta

from pydantic import ValidationError

from notion_copilot.domain.models import IAStatus
from notion_copilot.domain.rules import TemporaryFailure, is_retryable, is_stale
from tests.unit.application.fakes import make_card

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


def test_marks_a_running_card_stale_when_ia_atualizado_em_is_older_than_30_minutes():
    stale = make_card(
        ia_status=IAStatus.RODANDO,
        ia_updated_at=NOW - timedelta(minutes=31),
    )

    assert is_stale(stale, now=NOW, stale_after_s=1800.0) is True


def test_does_not_mark_a_running_card_stale_within_30_minutes():
    fresh = make_card(
        ia_status=IAStatus.RODANDO,
        ia_updated_at=NOW - timedelta(minutes=29),
    )
    not_running = make_card(ia_status=None, ia_updated_at=NOW - timedelta(hours=2))

    assert is_stale(fresh, now=NOW, stale_after_s=1800.0) is False
    assert is_stale(not_running, now=NOW, stale_after_s=1800.0) is False


def test_classifies_infrastructure_failures_as_retryable():
    assert is_retryable(TemporaryFailure("429 Too Many Requests")) is True
    assert is_retryable(TemporaryFailure("connection reset")) is True


def test_classifies_agent_invalid_json_and_notion_4xx_as_permanent():
    # JSON fora do contrato (ValidationError) e 4xx do Notion (traduzidos pelo
    # adapter como NÃO-TemporaryFailure) não repetem (research R8)
    assert is_retryable(ValidationError.from_exception_data("RefineOutput", [])) is False
    assert is_retryable(RuntimeError("APIResponseError: validation_error")) is False
    assert is_retryable(ValueError("stream-json sem evento result")) is False


def test_classifies_agent_timeout_as_permanent_no_retry():
    # decisão da usuária 2026-10-10 (research R8): timeout não repete
    assert is_retryable(TimeoutError("agente excedeu 600s")) is False
