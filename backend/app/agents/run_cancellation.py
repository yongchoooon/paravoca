from __future__ import annotations

from threading import Lock


_lock = Lock()
_requested_run_ids: set[str] = set()


def request_run_cancellation(run_id: str) -> None:
    with _lock:
        _requested_run_ids.add(run_id)


def clear_run_cancellation(run_id: str) -> None:
    with _lock:
        _requested_run_ids.discard(run_id)


def is_run_cancellation_requested(run_id: str) -> bool:
    with _lock:
        return run_id in _requested_run_ids
