"""Lock de rodada com fcntl.flock no diretório de estado (research R3).

O scheduler roda em uma única máquina (1 usuária), então um lock local é
suficiente. flock é atômico e liberado pelo sistema operacional em crash —
sem arquivo PID manual. A defesa em profundidade é o IA status ⏳ (FR-005).
"""

from __future__ import annotations

import fcntl
from pathlib import Path
from typing import IO


class FileRoundLock:
    def __init__(self, state_dir: Path) -> None:
        self._path = state_dir / "round.lock"
        self._fh: IO[str] | None = None

    def acquire(self) -> bool:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fh = self._path.open("a+")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fh.close()
            return False
        self._fh = fh
        return True

    def release(self) -> None:
        if self._fh is None:
            return
        fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        self._fh.close()
        self._fh = None
