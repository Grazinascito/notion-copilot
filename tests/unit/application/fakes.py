"""Fakes dos ports para os testes do núcleo (RNF-M3: sem rede, sem Notion, sem modelo).

Todos registram chamadas em um journal compartilhado para testes de ordem
(ex.: ⏳ marcado antes de invocar o agente).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from notion_copilot.domain.models import Card, IAStatus, Pipeline

Journal = list[tuple[str, str, Any]]

# Página criada a partir do template do banco (research R1): esqueleto vazio.
SKELETON_MARKDOWN = "\n".join(
    [
        "## 🔍 Refinamento — 10/10/2026 11:00",
        "### Contexto",
        "### Links guardados",
        "### Ações sugeridas",
        "### O que já adiantei",
        "### Perguntas abertas",
        "### Prompt sugerido",
        "### Executor sugerido",
    ]
)

GOLDEN_AGENT_OUTPUT = {
    "title": "Ligar para a Estácio sobre bolsa do curso",
    "sections": {
        "contexto": "**Síntese.** Você quer ligar para a Estácio sobre a bolsa.",
        "links_guardados": "- [Bolsas Estácio](https://estacio.br/bolsas) — página oficial",
        "acoes_sugeridas": "- [ ] Reunir dados antes de ligar",
        "o_que_ja_adiantei": "Fonte: página oficial de bolsas.",
        "perguntas_abertas": "1. Você já é aluno? (sim / não)",
        "prompt_sugerido": "Sem prompt sugerido: a execução depende de ação humana.",
        "executor_sugerido": "Humano — a ligação precisa da sua voz.",
    },
    "blocking_questions": [],
    "executor_suggestion": "HUMANO",
}


def golden_agent_json(blocking: list[str] | None = None) -> str:
    payload = json.loads(json.dumps(GOLDEN_AGENT_OUTPUT))
    if blocking is not None:
        payload["blocking_questions"] = blocking
    return json.dumps(payload, ensure_ascii=False)


def make_card(
    page_id: str = "card-1",
    *,
    pipeline: Pipeline = Pipeline.TO_REFINE,
    ia_status: IAStatus | None = None,
    executor: str | None = None,
    title: str = "ligar pra estacio pra saber como pegar bolsa do curso",
    created_at: datetime = datetime(2026, 10, 10, 11, 0),
    ia_updated_at: datetime | None = None,
) -> Card:
    return Card(
        page_id=page_id,
        title=title,
        pipeline=pipeline,
        executor=executor,
        ia_status=ia_status,
        ia_updated_at=ia_updated_at,
        created_at=created_at,
        body_markdown="",
    )


class FakeClock:
    def __init__(self, now: datetime = datetime(2026, 10, 10, 12, 0)) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class FakeLock:
    def __init__(self, busy: bool = False) -> None:
        self.busy = busy
        self.acquired = False
        self.released = False

    def acquire(self) -> bool:
        if self.busy:
            return False
        self.acquired = True
        return True

    def release(self) -> None:
        self.released = True


class FakeReader:
    """Devolve tudo que tem; a regra de seleção é do domínio (FR-004)."""

    def __init__(
        self,
        cards: list[Card],
        markdown: str = "corpo original do card",
        journal: Journal | None = None,
        stale_cards: list[Card] | None = None,
        get_card_overrides: dict[str, Card] | None = None,
        flaky_markdown_reads: int = 0,
    ) -> None:
        self._cards = cards
        self._markdown = markdown
        self._journal = journal if journal is not None else []
        self._stale_cards = stale_cards or []
        self._overrides = get_card_overrides or {}
        self._flaky_reads = flaky_markdown_reads
        self.query_calls = 0
        self.stale_query_calls = 0

    def get_card(self, page_id: str) -> Card:
        self._journal.append(("reader", "get_card", page_id))
        if page_id in self._overrides:
            return self._overrides[page_id]
        return next(c for c in self._cards if c.page_id == page_id)

    def query_eligible(self, limit: int) -> list[Card]:
        self.query_calls += 1
        self._journal.append(("reader", "query_eligible", limit))
        return list(self._cards)

    def query_stale_running(self, older_than_s: float) -> list[Card]:
        self.stale_query_calls += 1
        self._journal.append(("reader", "query_stale_running", older_than_s))
        return list(self._stale_cards)

    def get_page_markdown(self, page_id: str) -> str:
        self._journal.append(("reader", "get_page_markdown", page_id))
        if self._flaky_reads > 0:
            self._flaky_reads -= 1
            from notion_copilot.domain.rules import TemporaryFailure

            raise TemporaryFailure("429 Too Many Requests")
        return self._markdown


class FakeWriter:
    def __init__(self, journal: Journal | None = None) -> None:
        self._journal = journal if journal is not None else []
        self.ia_status_calls: list[tuple[str, IAStatus | None, datetime]] = []
        self.updates: list[tuple[str, list]] = []
        self.appends: list[tuple[str, str]] = []
        self.titles: list[tuple[str, str]] = []
        self.executors: list[tuple[str, str]] = []
        self.moved: list[str] = []
        self.comments: list[tuple[str, str, str]] = []

    def set_ia_status(
        self, page_id: str, status: IAStatus | None, now: datetime
    ) -> None:
        self.ia_status_calls.append((page_id, status, now))
        self._journal.append(("writer", "set_ia_status", status))

    def apply_markdown_updates(self, page_id: str, updates: list) -> None:
        self.updates.append((page_id, list(updates)))
        self._journal.append(("writer", "apply_markdown_updates", len(updates)))

    def append_markdown(self, page_id: str, markdown: str) -> None:
        self.appends.append((page_id, markdown))
        self._journal.append(("writer", "append_markdown", markdown[:40]))

    def set_title(self, page_id: str, title: str) -> None:
        self.titles.append((page_id, title))
        self._journal.append(("writer", "set_title", title))

    def set_executor(self, page_id: str, executor: str) -> None:
        self.executors.append((page_id, executor))
        self._journal.append(("writer", "set_executor", executor))

    def move_to_refined(self, page_id: str) -> None:
        self.moved.append(page_id)
        self._journal.append(("writer", "move_to_refined", page_id))

    def add_comment(self, page_id: str, text: str, mention_user_id: str) -> None:
        self.comments.append((page_id, text, mention_user_id))
        self._journal.append(("writer", "add_comment", text[:40]))


class FakeAgent:
    def __init__(self, raw, journal: Journal | None = None) -> None:
        # raw: string fixa, ou callable(card_id) -> string (respostas por card)
        self.raw = raw
        self._journal = journal if journal is not None else []
        self.prompts: list[str] = []

    def run_refine(self, prompt: str, run_id: str, card_id: str) -> str:
        self.prompts.append(prompt)
        self._journal.append(("agent", "run_refine", card_id))
        if callable(self.raw):
            return self.raw(card_id)
        return self.raw
