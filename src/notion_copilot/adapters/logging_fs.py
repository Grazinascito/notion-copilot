"""Eventos JSON locais + rastro do agente no diretório de estado (RNF-O1–O5).

Cada evento é uma linha JSON com ts, run_id, card_id (quando houver), stage,
event, duration_s e detail (opcionais). Nenhum campo pode conter segredo
(RNF-O5): chaves sensíveis são descartadas do detail antes da escrita — o log
não recebe token por parâmetro nenhum.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

_SENSITIVE_KEY = re.compile(r"(token|key|secret|password)", re.IGNORECASE)


class EventLog:
    def __init__(self, state_dir: Path) -> None:
        self._state_dir = state_dir
        self._events_path = state_dir / "logs" / "events.jsonl"

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
        record: dict[str, object] = {
            "ts": datetime.now(UTC).isoformat(),
            "run_id": run_id,
            "stage": stage,
            "event": event,
        }
        if card_id is not None:
            record["card_id"] = card_id
        if duration_s is not None:
            record["duration_s"] = duration_s
        if detail is not None:
            record["detail"] = _redact(detail)
        self._events_path.parent.mkdir(parents=True, exist_ok=True)
        with self._events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def save_agent_trail(self, *, run_id: str, card_id: str, raw: str) -> Path:
        """Salva o rastro stream-json de uma execução do agente (RNF-O3)."""
        trail_dir = self._trails_dir(run_id)
        trail_path = trail_dir / f"{card_id}.jsonl"
        trail_path.write_text(raw, encoding="utf-8")
        return trail_path

    def trail_path(self, *, run_id: str, card_id: str) -> Path:
        return self._trails_dir(run_id) / f"{card_id}.jsonl"

    def _trails_dir(self, run_id: str) -> Path:
        trail_dir = self._state_dir / "trails" / run_id
        trail_dir.mkdir(parents=True, exist_ok=True)
        return trail_dir


def _redact(detail: dict[str, object]) -> dict[str, object]:
    return {k: v for k, v in detail.items() if not _SENSITIVE_KEY.search(k)}
