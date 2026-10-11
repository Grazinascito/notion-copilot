"""Testes do adapter do Notion contra respostas gravadas (sem rede — RNF-M3).

O FakeNotionClient reproduz a superfície do notion-client usada pelo adapter;
os payloads são respostas reais gravadas da API.
"""

from __future__ import annotations

from datetime import UTC, datetime

from notion_copilot.adapters.notion_api import NotionApi
from notion_copilot.domain.models import IAStatus, MarkdownUpdate, Pipeline

PAGE_ID = "11111111-1111-1111-1111-111111111111"

RECORDED_PAGE = {
    "id": PAGE_ID,
    "created_time": "2026-10-10T11:00:00+00:00",
    "properties": {
        "Name": {
            "type": "title",
            "title": [{"plain_text": "ligar pra estacio pra saber da bolsa"}],
        },
        "Pipeline": {"type": "select", "select": {"name": "TO REFINE"}},
        "Executor": {"type": "select", "select": None},
        "IA status": {"type": "select", "select": None},
        "IA atualizado em": {"type": "date", "date": None},
    },
}

RECORDED_DATABASE = {
    "id": "db-1",
    "title": [{"plain_text": "Inbox"}],
    "properties": {
        "Name": {"type": "title"},
        "Pipeline": {
            "type": "select",
            "select": {"options": [{"name": "TO REFINE"}, {"name": "REFINED"}]},
        },
        "Executor": {
            "type": "select",
            "select": {"options": [{"name": "Humano"}, {"name": "IA"}]},
        },
        "IA status": {
            "type": "select",
            "select": {
                "options": [
                    {"name": "⏳ rodando"},
                    {"name": "❓ precisa de você"},
                    {"name": "⚠️ erro"},
                ]
            },
        },
        "IA atualizado em": {"type": "date", "date": {}},
    },
}


SKELETON_MARKDOWN = "\n".join(
    [
        "## 📝 Captura",  # conteúdo qualquer antes
        "## 🔍 Refinamento",
        "### Contexto",
        "### Links guardados",
        "### Ações sugeridas",
        "### O que já adiantei",
        "### Perguntas abertas",
        "### Prompt sugerido",
        "### Executor sugerido",
    ]
)


class FakeEndpoint:
    def __init__(self, calls: list, name: str, response) -> None:
        self._calls = calls
        self._name = name
        self._response = response

    def __call__(self, **kwargs):
        self._calls.append((self._name, kwargs))
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class _NS:
    pass


class FakeNotionClient:
    def __init__(
        self,
        *,
        me_response=None,
        database_response=None,
        query_response=None,
        markdown=SKELETON_MARKDOWN,
    ) -> None:
        self.calls: list = []
        users = _NS()
        users.me = FakeEndpoint(
            self.calls, "users.me", me_response or {"object": "user", "name": "copilot"}
        )
        data_sources = _NS()
        data_sources.retrieve = FakeEndpoint(
            self.calls, "data_sources.retrieve", database_response or RECORDED_DATABASE
        )
        data_sources.query = FakeEndpoint(
            self.calls,
            "data_sources.query",
            query_response if query_response is not None else {"results": [RECORDED_PAGE]},
        )
        pages = _NS()
        pages.retrieve = FakeEndpoint(self.calls, "pages.retrieve", RECORDED_PAGE)
        pages.update = FakeEndpoint(self.calls, "pages.update", {"object": "page"})
        pages.retrieve_markdown = FakeEndpoint(
            self.calls, "pages.retrieve_markdown", {"markdown": markdown}
        )
        pages.update_markdown = FakeEndpoint(
            self.calls, "pages.update_markdown", {"object": "page"}
        )
        comments = _NS()
        comments.create = FakeEndpoint(self.calls, "comments.create", {"object": "comment"})
        self.users = users
        self.data_sources = data_sources
        self.pages = pages
        self.comments = comments


def make_api(client=None, markdown: str = SKELETON_MARKDOWN) -> NotionApi:
    return NotionApi(
        auth_token="secret-x",
        database_id="db-1",
        client=client if client is not None else FakeNotionClient(markdown=markdown),
    )


def test_queries_eligible_cards_with_the_server_side_filter_and_translates_them():
    api = make_api()

    cards = api.query_eligible(5)

    (name, kwargs), *_ = [c for c in api._client.calls if c[0] == "data_sources.query"]
    assert kwargs["filter"] == {
        "and": [
            {"property": "Pipeline", "select": {"equals": "TO REFINE"}},
            {"property": "IA status", "select": {"is_empty": True}},
        ]
    }
    assert kwargs["page_size"] == 100
    assert "sorts" not in kwargs

    assert len(cards) == 1
    card = cards[0]
    assert card.page_id == PAGE_ID
    assert card.title == "ligar pra estacio pra saber da bolsa"
    assert card.pipeline == Pipeline.TO_REFINE
    assert card.executor is None
    assert card.ia_status is None
    assert card.created_at == datetime(2026, 10, 10, 11, 0, tzinfo=UTC)


def test_reads_the_page_markdown_through_the_markdown_endpoint():
    api = make_api()

    markdown = api.get_page_markdown(PAGE_ID)

    assert "## 🔍 Refinamento" in markdown
    calls = [c for c in api._client.calls if c[0] == "pages.retrieve_markdown"]
    assert calls[0][1] == {"page_id": PAGE_ID}


def test_applies_update_content_operations_through_the_markdown_endpoint():
    api = make_api()

    api.apply_markdown_updates(
        PAGE_ID,
        [
            MarkdownUpdate(old_str="### Contexto", new_str="### Contexto\nCorpo."),
            MarkdownUpdate(old_str="### Links guardados", new_str="### Links guardados\n- x"),
        ],
    )

    (name, kwargs), *_ = [c for c in api._client.calls if c[0] == "pages.update_markdown"]
    assert kwargs == {
        "page_id": PAGE_ID,
        "commands": [
            {"type": "update_content", "old_str": "### Contexto", "new_str": "### Contexto\nCorpo."},
            {
                "type": "update_content",
                "old_str": "### Links guardados",
                "new_str": "### Links guardados\n- x",
            },
        ],
    }


def test_writes_ia_status_together_with_ia_atualizado_em_in_one_call():
    api = make_api()
    now = datetime(2026, 10, 10, 12, 0)

    api.set_ia_status(PAGE_ID, IAStatus.RODANDO, now)

    (name, kwargs), *_ = [c for c in api._client.calls if c[0] == "pages.update"]
    assert kwargs["page_id"] == PAGE_ID
    assert kwargs["properties"] == {
        "IA status": {"select": {"name": "⏳ rodando"}},
        "IA atualizado em": {"date": {"start": "2026-10-10T12:00:00"}},
    }


def test_moves_the_card_to_the_refined_pipeline():
    api = make_api()

    api.move_to_refined(PAGE_ID)

    (name, kwargs), *_ = [c for c in api._client.calls if c[0] == "pages.update"]
    assert kwargs["properties"]["Pipeline"] == {"select": {"name": "REFINED"}}


def test_check_problems_reports_missing_properties_with_a_fix_hint():
    broken = RECORDED_DATABASE.copy()
    broken_props = dict(RECORDED_DATABASE["properties"])
    del broken_props["IA status"]
    broken = {**RECORDED_DATABASE, "properties": broken_props}
    api = make_api(FakeNotionClient(database_response=broken))

    problems = api.check_problems()

    assert any("IA status" in problem for problem in problems)


def test_appends_the_refinement_skeleton_via_insert_content():
    api = make_api()

    api.append_markdown(PAGE_ID, "## 🔍 Refinamento — 10/10/2026 12:00\n### Contexto\nx")

    (name, kwargs), *_ = [
        c for c in api._client.calls if c[0] == "pages.update_markdown"
    ]
    assert kwargs == {
        "page_id": PAGE_ID,
        "commands": [
            {
                "type": "insert_content",
                "position": "end",
                "content": "## 🔍 Refinamento — 10/10/2026 12:00\n### Contexto\nx",
            }
        ],
    }


def test_check_problems_passes_on_a_valid_database():
    api = make_api()

    assert api.check_problems() == []
