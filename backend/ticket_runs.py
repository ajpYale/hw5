"""Runs the agent team in the background so POST /tickets/{id}/run returns at once.

Each run gets its own thread and event loop. On Windows that loop is a
ProactorEventLoop, the only kind that can spawn the MCP server subprocess
(uvicorn --reload may use a selector loop for the app itself).
"""

import asyncio
import sys
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from backend.run_ticket import work_ticket


@dataclass
class RunState:
    ticket_id: int
    session_id: str
    status: str  # running | done | failed
    started_at: str
    finished_at: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None


_runs: dict[int, RunState] = {}  # latest run per ticket
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _loop_factory() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop()
    return asyncio.new_event_loop()


def _run(state: RunState) -> None:
    try:
        with asyncio.Runner(loop_factory=_loop_factory) as runner:
            resolution = runner.run(work_ticket(state.ticket_id, state.session_id))
        state.result = resolution.model_dump(mode="json")
        state.status = "done"
    except Exception as exc:  # recorded in the audit trail too
        state.error = f"{type(exc).__name__}: {exc}"
        state.status = "failed"
    finally:
        state.finished_at = _now()


def start(ticket_id: int) -> RunState:
    """Start a run, or raise RuntimeError if this ticket is already running."""
    with _lock:
        current = _runs.get(ticket_id)
        if current and current.status == "running":
            raise RuntimeError(f"Ticket {ticket_id} is already running ({current.session_id}).")
        state = RunState(
            ticket_id=ticket_id,
            session_id=uuid.uuid4().hex[:12],
            status="running",
            started_at=_now(),
        )
        _runs[ticket_id] = state
    threading.Thread(target=_run, args=(state,), daemon=True, name=f"ticket-{ticket_id}").start()
    return state


def latest(ticket_id: int) -> dict[str, Any] | None:
    state = _runs.get(ticket_id)
    return asdict(state) if state else None


def any_running() -> bool:
    return any(s.status == "running" for s in _runs.values())


def clear() -> None:
    with _lock:
        _runs.clear()
