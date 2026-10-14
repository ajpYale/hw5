"""Turns audit-trail records into short events the frontend can poll."""

from datetime import datetime, timezone
from typing import Any

from backend.audit import read_records

OUTPUT_TOOL = "final_result"


def _message(record: dict[str, Any]) -> str:
    output = record.get("output")
    if record["event"] == "error":
        return f"Error: {output}"
    if record["event"] == "final":
        if isinstance(output, dict) and output.get("summary"):
            return output["summary"]
        return str(output)

    parts = []
    if isinstance(output, str) and output.strip():
        parts.append(output.strip())
    for call in record["tool_calls"]:
        if call["delegation_target"]:
            request = str(call["args"].get("request", ""))
            parts.append(f"Delegated to {call['delegation_target']}: {request}")
    tools = [c["tool"] for c in record["tool_calls"] if not c["delegation_target"]]
    if tools:
        parts.append("Called " + ", ".join(tools))
    return " | ".join(parts) or "Thinking"


def to_event(record: dict[str, Any], event_id: int) -> dict[str, Any]:
    return {
        "id": event_id,
        "timestamp": record["timestamp"],
        "ticket_id": record["ticket_id"],
        "session_id": record["session_id"],
        "agent": record["agent"],
        "delegated_by": record["delegated_by"],
        "depth": record["depth"],
        "step": record["step"],
        "kind": record["event"],  # step | final | error
        "message": _message(record),
        "tools_used": [c["tool"] for c in record["tool_calls"] if c["tool"] != OUTPUT_TOOL],
        "tool_calls": [
            {"tool": c["tool"], "args": c["args"]}
            for c in record["tool_calls"]
            if c["tool"] != OUTPUT_TOOL
        ],
        "delegated_to": record["delegation_targets"],
        "tokens": record["step_usage"]["total_tokens"],
        # the agent's structured report (SpecialistReport / TicketResolution) on its last step
        "result": record["output"] if record["event"] == "final" else None,
    }


def events(ticket_id: int | None = None, since: str | None = None) -> list[dict[str, Any]]:
    """Events oldest-first. `since` is an event id (int) or an ISO timestamp.

    An event's id is its position in the append-only audit trail, so polling
    with `since=<last id seen>` never misses or repeats an event.
    """
    since_id: int | None = None
    since_ts: datetime | None = None
    if since:
        if since.lstrip("-").isdigit():
            since_id = int(since)
        else:
            since_ts = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if since_ts.tzinfo is None:  # audit timestamps are UTC
                since_ts = since_ts.replace(tzinfo=timezone.utc)

    out = []
    for event_id, record in enumerate(read_records()):
        if ticket_id is not None and record["ticket_id"] != ticket_id:
            continue
        if since_id is not None and event_id <= since_id:
            continue
        if since_ts is not None and datetime.fromisoformat(record["timestamp"]) <= since_ts:
            continue
        out.append(to_event(record, event_id))
    return out
