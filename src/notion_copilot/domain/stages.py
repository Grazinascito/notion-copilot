"""Tabela de etapas do pipeline — fonte única do conhecimento por etapa.

Constituição IX: adicionar uma etapa nova exige somente um prompt em prompts/ e
uma linha aqui, sem tocar o loop principal. Constituição III: a allowlist de
ferramentas é garantida pelo adapter via --allowedTools, nunca pelo prompt.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Stage:
    name: str
    prompt_file: str  # relativo a prompts/
    allowed_tools: tuple[str, ...]  # prefixos passados ao --allowedTools


STAGES: dict[str, Stage] = {
    "refine": Stage(
        name="refine",
        prompt_file="refine.md",
        allowed_tools=("mcp__web_search_prime", "mcp__web_reader"),
    ),
}
