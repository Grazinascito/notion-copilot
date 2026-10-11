"""Adapter do Claude Code CLI — único arquivo que conhece as flags do CLI e o
stream-json (constituição IV). Invocação como subprocesso (ADR-004, research R5).

A credencial é passada SOMENTE ao ambiente do subprocesso (RNF-S6); o
${ANTHROPIC_AUTH_TOKEN} do .mcp.json é expandido pelo próprio CLI a partir
desse ambiente.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from notion_copilot.adapters.logging_fs import EventLog
from notion_copilot.domain.stages import STAGES


class ClaudeCliRunner:
    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        auth_token: str,
        mcp_config_path: Path,
        timeout_s: float,
        max_turns: int,
        events: EventLog,
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._auth_token = auth_token
        self._mcp_config_path = mcp_config_path
        self._timeout_s = timeout_s
        self._max_turns = max_turns
        self._events = events

    def run_refine(self, prompt: str, run_id: str, card_id: str) -> str:
        stage = STAGES["refine"]
        cmd = [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--allowedTools",
            *stage.allowed_tools,
            "--mcp-config",
            str(self._mcp_config_path),
            "--max-turns",
            str(self._max_turns),
            "--model",
            self._model,
        ]
        env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", str(Path.home())),
            "ANTHROPIC_BASE_URL": self._base_url,
            "ANTHROPIC_AUTH_TOKEN": self._auth_token,
        }
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                f"agente excedeu o tempo limite de {self._timeout_s}s (RNF-C4)"
            ) from exc

        self._events.save_agent_trail(run_id=run_id, card_id=card_id, raw=proc.stdout or "")
        if proc.returncode != 0:
            raise RuntimeError(
                f"claude CLI terminou com código {proc.returncode}: "
                f"{(proc.stderr or '')[-500:]}"
            )
        return _final_result(proc.stdout)


def _final_result(stream: str) -> str:
    """Extrai o texto do último evento result do stream-json (RNF-O3 guarda o rastro)."""
    for line in reversed((stream or "").splitlines()):
        line = line.strip()
        if not line:
            continue
        event = json.loads(line)
        if event.get("type") == "result":
            result = event.get("result")
            if not isinstance(result, str):
                raise ValueError("evento result sem campo result")
            return result
    raise ValueError("stream-json sem evento result")


def check_problems() -> list[str]:
    """FR-002: executável do agente presente."""
    if shutil.which("claude") is None:
        return [
            "Executável do agente `claude` não encontrado no PATH. "
            "Instale o Claude Code CLI e autentique com o endpoint Z.ai (quickstart.md)."
        ]
    try:
        subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=30)
    except Exception as exc:
        return [f"`claude --version` falhou ({type(exc).__name__}): {exc}"]
    return []
