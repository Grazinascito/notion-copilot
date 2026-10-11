"""Ports (Protocols) — fronteira entre application e adapters (constituição II).

O application depende somente destas interfaces; os adapters as implementam.
Os testes do núcleo usam fakes destes ports, sem rede, Notion ou modelo (RNF-M3).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from notion_copilot.domain.models import Card, IAStatus, MarkdownUpdate


class Clock(Protocol):
    def now(self) -> datetime: ...


class EventSink(Protocol):
    def emit(
        self,
        *,
        run_id: str,
        stage: str,
        event: str,
        card_id: str | None = None,
        duration_s: float | None = None,
        detail: dict[str, object] | None = None,
    ) -> None:
        """Uma linha JSON de evento (RNF-O1). Implementado por adapters/logging_fs."""
        ...


class RoundLock(Protocol):
    def acquire(self) -> bool:
        """False se outra rodada segura o lock (FR-003)."""
        ...

    def release(self) -> None: ...


class NotionReader(Protocol):
    def get_card(self, page_id: str) -> Card: ...

    def query_eligible(self, limit: int) -> list[Card]:
        """Cards em To Refine com IA status vazio, mais antigos primeiro (FR-004)."""
        ...

    def query_stale_running(self, older_than_s: float) -> list[Card]:
        """Cards ⏳ cujo IA atualizado em é anterior ao corte (FR-017, R7)."""
        ...

    def get_page_markdown(self, page_id: str) -> str:
        """Markdown atual da página, base dos marcadores de idempotência (R9)."""
        ...


class NotionWriter(Protocol):
    def set_ia_status(
        self, page_id: str, status: IAStatus | None, now: datetime
    ) -> None:
        """Escreve IA status e reescreve IA atualizado em na mesma chamada."""
        ...

    def apply_markdown_updates(
        self, page_id: str, updates: list[MarkdownUpdate]
    ) -> None:
        """Aplica operações update_content no endpoint markdown (R1)."""
        ...

    def append_markdown(self, page_id: str, markdown: str) -> None:
        """Insere markdown ao fim da página — cria o esqueleto 🔍 quando a
        página não nasceu do template (ADR-008)."""
        ...

    def set_title(self, page_id: str, title: str) -> None: ...

    def set_executor(self, page_id: str, executor: str) -> None: ...

    def move_to_refined(self, page_id: str) -> None: ...

    def add_comment(self, page_id: str, text: str, mention_user_id: str) -> None:
        """Comentário com menção de user — dispara notificação (FR-014, R6)."""
        ...


class AgentRunner(Protocol):
    def run_refine(self, prompt: str, run_id: str, card_id: str) -> str:
        """Executa o agente da etapa Refine e devolve o texto final da resposta.

        Salva o rastro stream-json no log. O texto é validado como JSON
        RefineOutput pelo chamador (Pydantic na fronteira).
        """
        ...
