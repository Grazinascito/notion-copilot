"""Testes do lock de rodada com flock (research R3)."""

from notion_copilot.adapters.lock_fs import FileRoundLock


def test_reports_the_lock_busy_when_another_round_holds_it(tmp_path):
    first = FileRoundLock(state_dir=tmp_path)
    second = FileRoundLock(state_dir=tmp_path)

    assert first.acquire() is True
    try:
        assert second.acquire() is False
    finally:
        first.release()


def test_allows_acquiring_the_lock_again_after_release(tmp_path):
    lock = FileRoundLock(state_dir=tmp_path)

    assert lock.acquire() is True
    lock.release()

    again = FileRoundLock(state_dir=tmp_path)
    try:
        assert again.acquire() is True
    finally:
        again.release()
