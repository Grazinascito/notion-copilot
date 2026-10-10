"""Entidades do pipeline (data-model.md).

Domínio puro: nenhum import de IO, Notion ou Claude (constituição II).
Restrições citadas verbatim do data-model na forma de validação Pydantic:
nada entra no núcleo sem validação na fronteira.
"""

from __future__ import annotations

import secrets
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Pipeline(StrEnum):
    """Raias do board. Somente TO_REFINE é elegível (FR-004)."""

    TO_REFINE = "To Refine"
    PLAN = "Plan"
    AI_EXECUTE = "AI Execute"
    REFINED = "Refined"


class IAStatus(StrEnum):
    """Estados do trabalho da IA. Vazio (None) = elegível (FR-004/FR-005)."""

    RODANDO = "⏳ rodando"
    PRECISA_DE_VOCE = "❓ precisa de você"
    ERRO = "⚠️ erro"


class Executor(StrEnum):
    HUMANO = "Humano"
    IA = "IA"


CardOutcome = Literal[
    "success",
    "needs_you",
    "error",
    "skipped_moved",
    "skipped_already_refined",
]


class Card(BaseModel):
    page_id: str
    title: str
    pipeline: Pipeline
    executor: Executor | None = None
    ia_status: IAStatus | None = None
    ia_updated_at: datetime | None = None
    created_at: datetime
    body_markdown: str = ""
    has_refinement: bool = False
    has_original_record: bool = False


class CardResult(BaseModel):
    card_id: str
    outcome: CardOutcome
    error_kind: str | None = None
    # FR-016: 1 tentativa + até 2 novas tentativas
    attempts: int = Field(ge=1, le=3)
    duration_s: float


class Run(BaseModel):
    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    selected: list[Card] = Field(default_factory=list)
    results: list[CardResult] = Field(default_factory=list)


class MarkdownUpdate(BaseModel):
    """Operação de substituição do endpoint markdown (comando update_content, R1).

    Cada old_str precisa casar exatamente uma vez na página.
    """

    old_str: str
    new_str: str


REFINE_SECTION_KEYS: tuple[str, ...] = (
    "contexto",
    "links_guardados",
    "acoes_sugeridas",
    "o_que_ja_adiantei",
    "perguntas_abertas",
    "prompt_sugerido",
    "executor_sugerido",
)


class RefineOutput(BaseModel):
    """Saída validada do agente (contracts/agent-output.md).

    title: string não vazia, no máximo 80 caracteres; pode igualar a original.
    sections: exatamente as 7 chaves, corpos sem headings (os headings vêm do
    template da página).
    blocking_questions: não vazio faz o card terminar ❓ (decisão do código, R11).
    """

    title: str = Field(min_length=1, max_length=80)
    sections: dict[str, str]
    blocking_questions: list[str] = Field(default_factory=list)
    executor_suggestion: Literal["HUMANO", "IA"]

    @field_validator("sections")
    @classmethod
    def require_exactly_the_seven_sections(
        cls, value: dict[str, str]
    ) -> dict[str, str]:
        expected = set(REFINE_SECTION_KEYS)
        got = set(value)
        missing = expected - got
        extra = got - expected
        if missing or extra:
            raise ValueError(
                f"sections deve ter exatamente as 7 chaves {sorted(expected)}; "
                f"faltaram {sorted(missing)}, sobraram {sorted(extra)}"
            )
        return value


def new_run_id(now: datetime) -> str:
    """Formato do data-model: YYYYMMDDTHHMM-xxxx (ex.: 20261010T1425-7f3a)."""
    return f"{now.strftime('%Y%m%dT%H%M')}-{secrets.token_hex(2)}"
