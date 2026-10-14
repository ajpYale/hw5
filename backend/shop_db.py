"""Database access for the human-facing API (backend/main.py).

Agents never import this module; they only see the MCP server. `approve()` is
the one place in the whole system that writes `payments` or changes a cash
balance, and it only runs when a human calls POST /approvals/{id}/approve.
"""

import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from backend.config import ORIGINAL_DB_PATH
from mcp_server.server import APPROVAL_TABLE_SQL, DB_PATH

MONEY_KINDS = {"rent", "invoice", "purchase_order"}  # price_override moves no cash


class ApprovalError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


@contextmanager
def _connect(readonly: bool = True) -> Iterator[sqlite3.Connection]:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Working database not found at {DB_PATH}")
    mode = "ro" if readonly else "rw"
    conn = sqlite3.connect(
        f"file:{DB_PATH.as_posix()}?mode={mode}", uri=True, timeout=10, isolation_level=None
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def _has_approvals(conn: sqlite3.Connection) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'approval_requests'"
    ).fetchone() is not None


# "open" = the agent team still has work to do. Every other status means the team
# has finished: either it's fully resolved or it's waiting on a human (an
# approval, the customer, a vendor), and the detailed status says which.
STILL_OPEN = {"open", "in_progress"}


def list_tickets() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, subject, type, requester, status FROM tickets ORDER BY id"
        ).fetchall()
    return [
        {
            "id": r["id"],
            "title": r["subject"],
            "type": r["type"],
            "requester": r["requester"],
            "status": "open" if r["status"] in STILL_OPEN else "resolved",
            "detailed_status": r["status"],
        }
        for r in rows
    ]


def ticket_exists(ticket_id: int) -> bool:
    with _connect() as conn:
        return conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is not None


def list_approvals(status: str = "pending") -> list[dict[str, Any]]:
    with _connect() as conn:
        if not _has_approvals(conn):  # no agent has prepared anything yet
            return []
        rows = conn.execute(
            "SELECT * FROM approval_requests WHERE status = ? ORDER BY id", (status,)
        ).fetchall()
    return [{**dict(r), "moves_cash": r["kind"] in MONEY_KINDS} for r in rows]


def get_cash(account: str = "checking") -> dict[str, Any]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT name, balance, date FROM cash_accounts WHERE name = ?", (account,)
        ).fetchone()
        if row is None:
            raise LookupError(f"No cash account named '{account}'.")
        pending = 0.0
        if _has_approvals(conn):
            pending = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM approval_requests "
                "WHERE status = 'pending' AND kind IN ('rent', 'invoice', 'purchase_order')"
            ).fetchone()[0]
    return {
        "account": row["name"],
        "balance": row["balance"],
        "as_of": row["date"],
        "pending_outflow": round(float(pending), 2),
        "balance_if_all_pending_approved": round(row["balance"] - pending, 2),
    }


def approve(request_id: int, approved_by: str) -> dict[str, Any]:
    """Approve one prepared request. The only code path where cash moves.

    rent / invoice / purchase_order: re-checks the amount against the DB,
    refuses if the account can't cover it, writes a `payments` row (paid_at =
    desk.date_today), deducts the amount from the account, marks an invoice
    'paid' or advances the lease's next_due by a month, and marks the request
    'approved'. price_override: marks it approved; no cash moves. If that was
    the ticket's last pending request and the ticket was 'waiting_on_approval',
    the ticket becomes 'resolved'.
    All of it happens in one transaction, so it either fully applies or not at all.
    """
    with _connect(readonly=False) as conn:
        conn.execute(APPROVAL_TABLE_SQL)
        conn.execute("BEGIN IMMEDIATE")
        try:
            result = _approve(conn, request_id, approved_by)
            conn.execute("COMMIT")
            return result
        except Exception:
            conn.execute("ROLLBACK")
            raise


def _approve(conn: sqlite3.Connection, request_id: int, approved_by: str) -> dict[str, Any]:
    req = conn.execute("SELECT * FROM approval_requests WHERE id = ?", (request_id,)).fetchone()
    if req is None:
        raise ApprovalError(404, f"No approval request with id {request_id}.")
    if req["status"] != "pending":
        raise ApprovalError(409, f"Request {request_id} is already '{req['status']}'.")
    today = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()[0]
    decided_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def mark_approved() -> dict[str, Any]:
        conn.execute(
            "UPDATE approval_requests SET status = 'approved', decided_by = ?, decided_at = ? "
            "WHERE id = ?",
            (approved_by, decided_at, request_id),
        )
        _close_ticket_if_done(conn, req["ticket_id"], request_id, approved_by, today)
        return dict(
            conn.execute("SELECT * FROM approval_requests WHERE id = ?", (request_id,)).fetchone()
        )

    if req["kind"] == "price_override":
        return {"approval_request": mark_approved(), "cash_moved": False, "payment": None}

    if req["kind"] == "rent":
        lease = conn.execute("SELECT * FROM leases WHERE id = ?", (req["ref_id"],)).fetchone()
        if lease is None:
            raise ApprovalError(409, f"Lease {req['ref_id']} no longer exists.")
        amount, pay_ref = lease["monthly_rent"], lease["id"]
    elif req["kind"] == "invoice":
        inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (req["ref_id"],)).fetchone()
        if inv is None:
            raise ApprovalError(409, f"Invoice {req['ref_id']} no longer exists.")
        if inv["status"] != "open":
            raise ApprovalError(409, f"Invoice {inv['id']} is '{inv['status']}', not 'open'.")
        amount, pay_ref = inv["amount"], inv["id"]
    elif req["kind"] == "purchase_order":
        amount, pay_ref = req["amount"], req["id"]  # vendor is paid up front for the reprint
    else:
        raise ApprovalError(409, f"Unknown request kind '{req['kind']}'.")

    if round(amount, 2) != round(req["amount"], 2):
        raise ApprovalError(
            409, f"Amount on file is now ${amount:,.2f}, not the ${req['amount']:,.2f} prepared."
        )

    account = req["account"] or "checking"
    acct = conn.execute(
        "SELECT name, balance FROM cash_accounts WHERE name = ?", (account,)
    ).fetchone()
    if acct is None:
        raise ApprovalError(409, f"No cash account named '{account}'.")
    if acct["balance"] < amount:
        raise ApprovalError(
            409, f"'{account}' has ${acct['balance']:,.2f}; it can't cover ${amount:,.2f}."
        )

    cur = conn.execute(
        "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (req["kind"], pay_ref, amount, account, today, approved_by),
    )
    balance_after = round(acct["balance"] - amount, 2)
    conn.execute(
        "UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?",
        (balance_after, today, account),
    )
    if req["kind"] == "invoice":
        conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (pay_ref,))
    elif req["kind"] == "rent":
        conn.execute(
            "UPDATE leases SET next_due = date(next_due, '+1 month') WHERE id = ?", (pay_ref,)
        )

    payment = conn.execute("SELECT * FROM payments WHERE id = ?", (cur.lastrowid,)).fetchone()
    return {
        "approval_request": mark_approved(),
        "cash_moved": True,
        "payment": dict(payment),
        "account": account,
        "balance_before": acct["balance"],
        "balance_after": balance_after,
    }


def _close_ticket_if_done(
    conn: sqlite3.Connection, ticket_id: int, request_id: int, approved_by: str, today: str
) -> None:
    """A ticket parked on 'waiting_on_approval' is resolved once its last request is approved."""
    ticket = conn.execute("SELECT status, notes FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if ticket is None or ticket["status"] != "waiting_on_approval":
        return
    still_pending = conn.execute(
        "SELECT COUNT(*) FROM approval_requests WHERE ticket_id = ? AND status = 'pending'",
        (ticket_id,),
    ).fetchone()[0]
    if still_pending:
        return
    entry = f"[{today} {approved_by}] Approved request #{request_id}; nothing left pending."
    notes = f"{ticket['notes']}\n{entry}" if ticket["notes"] else entry
    conn.execute(
        "UPDATE tickets SET status = 'resolved', notes = ? WHERE id = ?", (notes, ticket_id)
    )


def reset() -> dict[str, Any]:
    """Overwrite the working copy with the untouched original."""
    shutil.copyfile(ORIGINAL_DB_PATH, DB_PATH)
    return {"reset": True, "source": ORIGINAL_DB_PATH.name, "target": DB_PATH.name}
