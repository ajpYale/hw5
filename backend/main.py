"""Campus Customs desk API.

Start from inside backend/:
    uvicorn main:app --reload --port 8000

Agents never move money. The only route that changes cash is
POST /approvals/{id}/approve, which a human calls.
"""

import sys
from pathlib import Path

# Running from inside backend/ puts backend/ (not the project root) on sys.path;
# add the root so `backend.*` and `mcp_server.*` import the same way everywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from backend import event_feed, shop_db, ticket_runs  # noqa: E402

app = FastAPI(title="Campus Customs Desk API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ApproveBody(BaseModel):
    approved_by: str = Field(min_length=1, description="Name of the human approving.")


@app.get("/tickets")
def get_tickets():
    """The desk tickets with id, title and open/resolved status, plus the latest run."""
    return [{**t, "last_run": ticket_runs.latest(t["id"])} for t in shop_db.list_tickets()]


@app.post("/tickets/{ticket_id}/run", status_code=202)
def run_ticket(ticket_id: int):
    """Start the agent team on a ticket (the Boss goes first). Poll /events for progress."""
    if not shop_db.ticket_exists(ticket_id):
        raise HTTPException(404, f"No ticket with id {ticket_id}.")
    try:
        state = ticket_runs.start(ticket_id)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    return {
        "ticket_id": ticket_id,
        "session_id": state.session_id,
        "status": state.status,
        "poll": f"/events?ticket_id={ticket_id}",
    }


@app.get("/events")
def get_events(
    ticket_id: int | None = None,
    since: str | None = Query(None, description="Last event id seen, or an ISO timestamp."),
):
    """Agent events from the audit trail, oldest first, newer than `since`."""
    try:
        events = event_feed.events(ticket_id, since)
    except ValueError:
        raise HTTPException(400, "since must be an event id or an ISO timestamp.")
    return {"events": events, "last_id": events[-1]["id"] if events else None}


@app.get("/approvals")
def get_approvals():
    """Payments, purchase orders and price overrides the agents prepared, still pending."""
    return shop_db.list_approvals("pending")


@app.post("/approvals/{request_id}/approve")
def approve(request_id: int, body: ApproveBody):
    """A human approves a prepared request. The only place cash actually changes."""
    try:
        return shop_db.approve(request_id, body.approved_by.strip())
    except shop_db.ApprovalError as exc:
        raise HTTPException(exc.status_code, str(exc))


@app.get("/cash")
def get_cash():
    """Current checking balance, plus what's pending approval."""
    return shop_db.get_cash("checking")


@app.post("/reset")
def reset():
    """Copy data/campus_customs.db over data/campus_customs_new.db for a clean run.

    The audit trail is append-only, so it is kept; use `since` to see only new events.
    """
    if ticket_runs.any_running():
        raise HTTPException(409, "A ticket run is in progress; wait for it to finish.")
    result = shop_db.reset()
    ticket_runs.clear()
    return result
