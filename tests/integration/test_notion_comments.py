"""Testes do adapter de comentários e da tradução de erros (FR-014, R6, R8)."""

from __future__ import annotations

import pytest

from notion_copilot.domain.rules import TemporaryFailure
from tests.integration.test_notion_api import PAGE_ID, FakeNotionClient, make_api


class FakeAPIError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(f"{code}")
        self.code = code


def test_posts_a_comment_with_user_mention_and_run_id():
    api = make_api()

    api.add_comment(PAGE_ID, "⚠️ Falha (agent_invalid_json). Execução r1.", "user-123")

    (name, kwargs), *_ = [c for c in api._client.calls if c[0] == "comments.create"]
    assert kwargs["parent"] == {"page_id": PAGE_ID}
    rich_text = kwargs["rich_text"]
    assert rich_text[0] == {
        "type": "mention",
        "mention": {"user": {"id": "user-123"}},
    }
    assert "Execução r1." in rich_text[1]["text"]["content"]


def test_translates_rate_limit_and_5xx_into_temporary_failure():
    def raising(code: str):
        def endpoint(**kwargs):
            raise FakeAPIError(code)

        return endpoint

    api = make_api(FakeNotionClient())
    api._client._inner.pages.update_markdown = raising("rate_limited")  # type: ignore[attr-defined]

    with pytest.raises(TemporaryFailure):
        api.append_markdown(PAGE_ID, "x")


def test_keeps_4xx_as_permanent():
    def raising(**kwargs):
        raise FakeAPIError("validation_error")

    api = make_api(FakeNotionClient())
    api._client._inner.pages.update_markdown = raising  # type: ignore[attr-defined]

    with pytest.raises(FakeAPIError):
        api.append_markdown(PAGE_ID, "x")


def test_comment_capability_problems_reports_missing_capability():
    def raising(**kwargs):
        raise FakeAPIError("unauthorized")

    client = FakeNotionClient()
    client.comments.create = raising  # type: ignore[method-assign]
    api = make_api(client)

    problems = api.comment_capability_problems()

    assert problems and "Insert comments" in problems[0]


def test_comment_capability_problems_passes_when_probe_comment_works():
    api = make_api()

    assert api.comment_capability_problems() == []
    deleted = [c for c in api._client.calls if c[0] == "comments.delete"]
    assert deleted, "o comentário de prova deve ser apagado"
