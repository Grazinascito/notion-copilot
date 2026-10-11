"""Configuração via .env (pydantic-settings) — research R3/R4/R5.

Credenciais vivem somente no .env com permissão 600 (RNF-S6); nenhuma saída
do programa imprime seus valores.
"""

from __future__ import annotations

import stat
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    notion_token: str = ""
    notion_database_id: str = ""
    notion_user_id: str = ""
    anthropic_auth_token: str = ""
    anthropic_base_url: str = "https://api.z.ai/api/anthropic"
    claude_model: str = "glm-5.3"

    # Constantes da rodada (plan.md Constraints; research R8)
    max_cards_per_round: int = 5
    agent_timeout_s: float = 600.0  # 10 min por card (RNF-C4)
    stale_after_s: float = 1800.0  # 30 min (FR-017)
    retry_backoff_s: list[int] = Field(default_factory=lambda: [30, 120])

    # Override do diretório de estado (testes; instalações alternativas)
    state_dir: Path | None = None

    @property
    def resolved_state_dir(self) -> Path:
        """Diretório de lock e logs (research R3), resolvido como absoluto."""
        if self.state_dir is not None:
            return self.state_dir.resolve()
        from platformdirs import user_state_dir

        return Path(user_state_dir("notion-copilot", appauthor=False))

    @property
    def mcp_config_path(self) -> Path:
        # launchd/cron executam com WorkingDirectory = raiz do projeto (R4);
        # caminho resolvido como absoluto porque o scheduler não herda CWD (R5).
        return Path(".mcp.json").resolve()

    @property
    def prompts_dir(self) -> Path:
        return Path("prompts").resolve()


def env_file_problem(env_path: Path) -> str | None:
    """Problema de permissão do .env com mensagem que diz como corrigir (FR-002).

    Retorna None quando o arquivo não existe (ausência é outra checagem do
    pré-flight) ou quando somente a dona pode lê-lo.
    """
    if not env_path.exists():
        return None
    mode = stat.S_IMODE(env_path.stat().st_mode)
    if mode & 0o077:
        return (
            f"O arquivo {env_path} tem permissões {format(mode, 'o')}; grupo e "
            f"outros não podem ler credenciais. Corrija com: chmod 600 {env_path}"
        )
    return None
