"""CLI (contracts/cli-commands.md): `notion-copilot run` e `notion-copilot verify`.

Raiz de composição: monta settings, adapters e o pré-flight. Exit codes do run:
0 concluída, 1 pré-flight, 2 lock ocupado, 3 cards em erro (agregação na US-3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import typer

from notion_copilot.adapters.claude_cli import ClaudeCliRunner
from notion_copilot.adapters.claude_cli import check_problems as claude_check
from notion_copilot.adapters.lock_fs import FileRoundLock
from notion_copilot.adapters.logging_fs import EventLog
from notion_copilot.adapters.notion_api import NotionApi
from notion_copilot.adapters.prompts_fs import load_prompt
from notion_copilot.application.run_round import run_round
from notion_copilot.config import Settings, env_file_problem
from notion_copilot.domain.stages import STAGES

app = typer.Typer(help="Orquestrador do board de inbox no Notion.", no_args_is_help=True)

REQUIRED_ENV: list[tuple[str, str]] = [
    ("notion_token", "NOTION_TOKEN"),
    ("notion_database_id", "NOTION_DATABASE_ID"),
    ("notion_user_id", "NOTION_USER_ID"),
    ("anthropic_auth_token", "ANTHROPIC_AUTH_TOKEN"),
]

MANUAL_REMINDERS = [
    "Capabilities da integração: habilite Read content, Update content e "
    "Insert comments em notion.so/my-integrations (research R1/R6) — sem elas, "
    "a API retorna 403.",
]


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def _env_problems(settings: Settings) -> list[str]:
    problems: list[str] = []
    env_path = Path(".env")
    if not env_path.exists():
        problems.append(
            ".env ausente. Copie o exemplo e proteja o arquivo: "
            "cp .env.example .env && chmod 600 .env"
        )
    permission = env_file_problem(env_path)
    if permission:
        problems.append(permission)
    for field_name, env_name in REQUIRED_ENV:
        if not getattr(settings, field_name):
            problems.append(f"{env_name} não definido no .env.")
    return problems


def _file_problems(settings: Settings) -> list[str]:
    problems: list[str] = []
    if not (settings.prompts_dir / STAGES["refine"].prompt_file).is_file():
        problems.append(
            f"prompt da etapa ausente: {settings.prompts_dir / 'refine.md'}"
        )
    if not settings.mcp_config_path.is_file():
        problems.append(f".mcp.json ausente em {settings.mcp_config_path}")
    return problems


def _preflight(settings: Settings, notion: NotionApi) -> list[str]:
    return (
        _env_problems(settings)
        + _file_problems(settings)
        + notion.check_problems()
        # sem template, todo card falharia na escrita com erro permanente (R1)
        + notion.template_skeleton_problems()
        + claude_check()
    )


@app.command()
def run(
    card: str = typer.Option(None, "--card", help="Processa só este card (page_id ou URL)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Lista o que faria, sem escrever."),
) -> None:
    """Executa uma rodada: lock → pré-flight → seleção (≤5) → processa."""
    settings = Settings()
    events = EventLog(state_dir=settings.resolved_state_dir)
    notion = NotionApi(
        auth_token=settings.notion_token,
        database_id=settings.notion_database_id,
    )
    claude = ClaudeCliRunner(
        model=settings.claude_model,
        base_url=settings.anthropic_base_url,
        auth_token=settings.anthropic_auth_token,
        mcp_config_path=settings.mcp_config_path,
        timeout_s=settings.agent_timeout_s,
        max_turns=20,
        events=events,
    )
    prompt_template = load_prompt(settings.prompts_dir, STAGES["refine"])

    code = run_round(
        settings=settings,
        reader=notion,
        writer=notion,
        agent=claude,
        clock=SystemClock(),
        lock=FileRoundLock(state_dir=settings.resolved_state_dir),
        events=events,
        prompt_template=prompt_template,
        preflight=lambda: _preflight(settings, notion),
        single_card=card,
        dry_run=dry_run,
    )
    raise typer.Exit(code)


@app.command()
def verify() -> None:
    """Pré-flight isolado (FR-002): lista ✔/✘ com o que falta e como corrigir."""
    settings = Settings()
    notion = NotionApi(
        auth_token=settings.notion_token,
        database_id=settings.notion_database_id,
    )

    failures: list[str] = []
    checks: list[tuple[str, list[str]]] = [
        ("arquivo .env e campos obrigatórios", _env_problems(settings)),
        ("arquivos prompts/refine.md e .mcp.json", _file_problems(settings)),
        ("token do Notion e banco do inbox", notion.check_problems()),
        ("template de página com o esqueleto 🔍", notion.template_skeleton_problems()),
        ("executável do agente (claude)", claude_check()),
    ]
    for label, problems in checks:
        if problems:
            failures.extend(problems)
            typer.echo(f"✘ {label}")
            for problem in problems:
                typer.echo(f"    {problem}")
        else:
            typer.echo(f"✔ {label}")

    for reminder in MANUAL_REMINDERS:
        typer.echo(f"ℹ {reminder}")

    raise typer.Exit(1 if failures else 0)


if __name__ == "__main__":
    app()
