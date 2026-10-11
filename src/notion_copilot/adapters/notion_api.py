"""Adapter do Notion — único arquivo que conhece a API do Notion (constituição IV).

Encapsula o SDK notion-client, incluindo os endpoints markdown da versão
2026-03-11 (research R1/R2): pages.retrieve_markdown / pages.update_markdown
com o comando update_content. Todos os erros da API propagam como exceções do
SDK; a classificação temporário/permanente é do domínio (rules).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, TypeVar

import notion_client

from notion_copilot.domain.models import (
    Card,
    Executor,
    IAStatus,
    MarkdownUpdate,
    Pipeline,
)

EXPECTED_PROPERTIES: dict[str, str] = {
    "Name": "title",
    "Pipeline": "select",
    "Executor": "select",
    "IA status": "select",
    "IA atualizado em": "date",
}

EXPECTED_IA_STATUS_OPTIONS = {
    IAStatus.RODANDO.value,
    IAStatus.PRECISA_DE_VOCE.value,
    IAStatus.ERRO.value,
}


class NotionApi:
    def __init__(
        self,
        *,
        auth_token: str,
        database_id: str,
        client: Any = None,
    ) -> None:
        # O SDK expõe endpoints dinâmicos (stubs incompletos); o cliente é Any
        # de propósito — este arquivo é o único que conhece a API (constituição IV).
        self._client: Any = (
            client if client is not None else notion_client.Client(auth=auth_token)
        )
        self._database_id = database_id

    # ----- NotionReader -------------------------------------------------

    def get_card(self, page_id: str) -> Card:
        page = self._client.pages.retrieve(page_id=page_id)
        return self._card_from_page(page)

    def query_eligible(self, limit: int) -> list[Card]:
        """FR-004/R7: filtro server-side — fila vazia custa 1 consulta.

        Sem sort server-side: a API nova não aceita o timestamp embutido
        `created_time` e o nome da propriedade de criação varia por board.
        Busca até 100 candidatas e a ordenação (mais antigos primeiro, limite
        `limit`) fica com a regra do domínio (select_cards), que é testada.
        """
        response = self._client.data_sources.query(
            data_source_id=self._database_id,
            filter={
                "and": [
                    {"property": "Pipeline", "select": {"equals": Pipeline.TO_REFINE.value}},
                    {"property": "IA status", "select": {"is_empty": True}},
                ]
            },
            page_size=100,
        )
        return [self._card_from_page(page) for page in response.get("results", [])]

    def query_stale_running(self, older_than_s: float) -> list[Card]:
        """FR-017/R7: ⏳ abandonados (IA atualizado em anterior ao corte)."""
        cutoff = datetime.now(UTC) - timedelta(seconds=older_than_s)
        response = self._client.data_sources.query(
            data_source_id=self._database_id,
            filter={
                "and": [
                    {
                        "property": "Pipeline",
                        "select": {"equals": Pipeline.TO_REFINE.value},
                    },
                    {"property": "IA status", "select": {"equals": IAStatus.RODANDO.value}},
                    {"property": "IA atualizado em", "date": {"before": cutoff.isoformat()}},
                ]
            },
            page_size=100,
        )
        return [self._card_from_page(page) for page in response.get("results", [])]

    def get_page_markdown(self, page_id: str) -> str:
        response = self._client.pages.retrieve_markdown(page_id=page_id)
        if isinstance(response, dict) and "markdown" in response:
            return str(response["markdown"])
        return str(response)

    # ----- NotionWriter -------------------------------------------------

    def set_ia_status(
        self, page_id: str, status: IAStatus | None, now: datetime
    ) -> None:
        """Invariante do data-model: IA atualizado em é reescrito a cada transição."""
        select = {"select": {"name": status.value}} if status else {"select": None}
        self._client.pages.update(
            page_id=page_id,
            properties={
                "IA status": select,
                "IA atualizado em": {"date": {"start": now.isoformat()}},
            },
        )

    def apply_markdown_updates(self, page_id: str, updates: list[MarkdownUpdate]) -> None:
        """R1: update_content — até 100 content_updates, old_str exato (schema
        verificado na API 2026-03-11: type no topo, comando aninhado)."""
        self._client.pages.update_markdown(
            page_id=page_id,
            type="update_content",
            update_content={
                "content_updates": [
                    {"old_str": update.old_str, "new_str": update.new_str}
                    for update in updates
                ]
            },
        )

    def append_markdown(self, page_id: str, markdown: str) -> None:
        """ADR-008: insere o esqueleto 🔍 completo ao fim da página.

        insert_content é legacy, mas é o comando que cria conteúdo novo —
        update_content só substitui o que existe.
        """
        self._client.pages.update_markdown(
            page_id=page_id,
            type="insert_content",
            insert_content={"content": markdown, "position": {"type": "end"}},
        )

    def set_title(self, page_id: str, title: str) -> None:
        self._client.pages.update(
            page_id=page_id,
            properties={"Name": {"title": [{"text": {"content": title}}]}},
        )

    def set_executor(self, page_id: str, executor: str) -> None:
        self._client.pages.update(
            page_id=page_id,
            properties={"Executor": {"select": {"name": executor}}},
        )

    def move_to_refined(self, page_id: str) -> None:
        self._client.pages.update(
            page_id=page_id,
            properties={"Pipeline": {"select": {"name": Pipeline.REFINED.value}}},
        )

    def add_comment(self, page_id: str, text: str, mention_user_id: str) -> None:
        """FR-014/R6: menção de user dispara notificação do Notion."""
        self._client.comments.create(
            parent={"page_id": page_id},
            rich_text=[
                {"type": "mention", "mention": {"user": {"id": mention_user_id}}},
                {"type": "text", "text": {"content": f" {text}"}},
            ],
        )

    # ----- pré-flight (FR-002) -------------------------------------------

    def check_problems(self) -> list[str]:
        """Token válido e banco com o schema esperado; cada problema diz como corrigir."""
        problems: list[str] = []
        try:
            self._client.users.me()
        except Exception as exc:
            problems.append(
                f"Token do Notion inválido ou sem acesso ({type(exc).__name__}). "
                "Verifique NOTION_TOKEN no .env e se a integração foi compartilhada "
                "com as páginas do board."
            )
            return problems

        try:
            database = self._client.data_sources.retrieve(data_source_id=self._database_id)
        except Exception as exc:
            problems.append(
                f"Banco {self._database_id} inacessível ({type(exc).__name__}). "
                "Verifique NOTION_DATABASE_ID e compartilhe o banco com a integração."
            )
            return problems

        properties: dict[str, Any] = database.get("properties", {})
        for prop_name, prop_type in EXPECTED_PROPERTIES.items():
            if prop_name not in properties:
                problems.append(
                    f"Propriedade '{prop_name}' ({prop_type}) ausente no banco. "
                    "Crie-a no board conforme specs/001-refine-happy-path/data-model.md."
                )
            elif properties[prop_name].get("type") != prop_type:
                problems.append(
                    f"Propriedade '{prop_name}' deveria ser {prop_type}, "
                    f"é {properties[prop_name].get('type')}. Corrija no board."
                )

        ia_status_prop = properties.get("IA status", {})
        options = {
            option.get("name", "")
            for option in ia_status_prop.get("select", {}).get("options", [])
        }
        missing_options = EXPECTED_IA_STATUS_OPTIONS - options
        if missing_options:
            problems.append(
                "IA status sem as opções esperadas "
                f"{sorted(missing_options)}. Crie-as no board (data-model.md)."
            )
        return problems

    # ----- tradução API → domínio ----------------------------------------

    def _card_from_page(self, page: dict[str, Any]) -> Card:
        properties = page.get("properties", {})
        pipeline = self._select_enum(properties.get("Pipeline", {}), Pipeline)
        if pipeline is None:
            raise ValueError(
                f"Pipeline ausente ou desconhecido na página {page.get('id')!r}"
            )
        rendered: dict[str, str] = {}
        for name, prop in properties.items():
            if name == "Name":
                continue  # título entregue em separado
            text = self._property_text(prop)
            if text is not None:
                rendered[name] = text
        return Card(
            page_id=page["id"],
            title=self._title_text(properties.get("Name", {})),
            pipeline=pipeline,
            executor=self._select_enum(properties.get("Executor", {}), Executor),
            ia_status=self._select_enum(properties.get("IA status", {}), IAStatus),
            ia_updated_at=self._date_value(properties.get("IA atualizado em", {})),
            created_at=_parse_datetime(page["created_time"]),
            body_markdown="",
            has_refinement=False,
            has_original_record=False,
            properties=rendered,
        )

    @staticmethod
    def _property_text(prop: dict[str, Any]) -> str | None:
        """Propriedade do Notion como texto legível; None para tipos que não
        fazem sentido no prompt (pessoas, métricas internas)."""
        ptype = prop.get("type")
        if ptype in ("title", "people", "created_by", "last_edited_by",
                     "created_time", "last_edited_time", "rollup", "formula",
                     "relation", "unique_id", "button"):
            return None
        if ptype in ("rich_text",):
            return "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))
        if ptype == "select":
            return (prop.get("select") or {}).get("name")
        if ptype == "status":
            return (prop.get("status") or {}).get("name")
        if ptype == "multi_select":
            names = [o.get("name", "") for o in prop.get("multi_select", [])]
            return ", ".join(n for n in names if n) or None
        if ptype == "date":
            date = prop.get("date") or {}
            if not date.get("start"):
                return None
            return date["end"] and f"{date['start']} a {date['end']}" or date["start"]
        if ptype in ("number", "checkbox", "url", "email", "phone_number"):
            value = prop.get(ptype)
            if value is None or value == "":
                return None
            return str(value)
        return None

    @staticmethod
    def _title_text(prop: dict[str, Any]) -> str:
        return "".join(part.get("plain_text", "") for part in prop.get("title", []))

    _EnumT = TypeVar("_EnumT", bound=StrEnum)

    @staticmethod
    def _select_enum(prop: dict[str, Any], enum_cls: type[_EnumT]) -> _EnumT | None:
        name = (prop.get("select") or {}).get("name")
        if name is None:
            return None
        try:
            return enum_cls(name)
        except ValueError:
            return None

    @staticmethod
    def _date_value(prop: dict[str, Any]) -> datetime | None:
        date = prop.get("date")
        if not date or not date.get("start"):
            return None
        return _parse_datetime(date["start"])


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
