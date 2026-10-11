"""Carrega os prompts versionados de prompts/ (constituição IX, RNF-M4).

O comportamento por etapa é artefato versionado; este módulo só lê o arquivo.
Os placeholders ({{TITULO}}, {{PROPRIEDADES}}, {{CORPO}}) são substituídos pelo
orquestrador em domain.rules.render_prompt.
"""

from __future__ import annotations

from pathlib import Path

from notion_copilot.domain.stages import Stage


def load_prompt(prompts_dir: Path, stage: Stage) -> str:
    path = prompts_dir / stage.prompt_file
    if not path.is_file():
        raise FileNotFoundError(
            f"Prompt da etapa {stage.name} ausente: {path} "
            f"(o arquivo é versionado no repositório — constituição IX)"
        )
    return path.read_text(encoding="utf-8")
