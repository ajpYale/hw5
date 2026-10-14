"""Campus Customs MCP server.

Exposes tools that let agents work the open desk tickets against the
working copy of the shop database (data/campus_customs_new.db).
Every value returned comes from the database; missing records produce
an {"error": ...} result instead of guessed data.
"""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# CAMPUS_CUSTOMS_DB lets tests point the server at a scratch copy.
DB_PATH = Path(
    os.environ.get("CAMPUS_CUSTOMS_DB") or PROJECT_ROOT / "data" / "campus_customs_new.db"
)

# Guardrails enforced server-side, so no prompt or agent can talk past them.
SPEND_CAP_PER_REQUEST = 2500.00  # largest single payment / purchase an agent may prepare
MAX_DISCOUNT_PCT = 25.0  # largest discount an agent may put up for approval
MIN_MARGIN_PCT = 30.0  # discounted price must keep at least this margin
AGENT_NAMES = {"boss", "inventory", "accounting", "facilities", "customer_service"}
TICKET_STATUSES = {
    "open",
    "in_progress",
    "waiting_on_approval",
    "waiting_on_customer",
    "waiting_on_vendor",
    "resolved",
}

# Agents may only PREPARE money movements. A prepared request lands here with
# status 'pending'; a human approves it through the API (POST
# /approvals/{id}/approve in backend/main.py), and only then is a row written
# to `payments` (whose paid_at/approved_by are NOT NULL).
APPROVAL_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS approval_requests (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    kind TEXT NOT NULL,
    ref_id INTEGER,
    vendor_id INTEGER REFERENCES vendors(id),
    sku TEXT,
    size TEXT,
    qty INTEGER,
    amount REAL NOT NULL,
    account TEXT,
    details TEXT,
    requested_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    decided_by TEXT,
    decided_at TEXT
)
"""

mcp = FastMCP("campus-customs", log_level="WARNING")


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """Open the working-copy DB read/write, commit on success, always close.

    Never creates a new file: mode=rw refuses to open a path that doesn't exist.
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Working database not found at {DB_PATH}")
    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=rw", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(APPROVAL_TABLE_SQL)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(approval_requests)")}
    for col in ("decided_by", "decided_at"):  # added after the table first shipped
        if col not in cols:
            conn.execute(f"ALTER TABLE approval_requests ADD COLUMN {col} TEXT")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _error(message: str) -> dict[str, Any]:
    return {"error": message}


def _today(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
    return row["date_today"] if row else None


def _days_between(conn: sqlite3.Connection, later: str, earlier: str) -> int:
    return conn.execute(
        "SELECT CAST(julianday(?) - julianday(?) AS INTEGER)", (later, earlier)
    ).fetchone()[0]


def _check_requester(requested_by: str) -> str | None:
    if requested_by not in AGENT_NAMES:
        return f"requested_by must be one of: {', '.join(sorted(AGENT_NAMES))}."
    return None


def _ticket_exists(conn: sqlite3.Connection, ticket_id: int) -> bool:
    return conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is not None


def _pending_request(
    conn: sqlite3.Connection, kind: str, ref_id: int
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM approval_requests WHERE kind = ? AND ref_id = ? AND status = 'pending'",
        (kind, ref_id),
    ).fetchone()


def _insert_request(conn: sqlite3.Connection, **fields: Any) -> dict[str, Any]:
    fields["created_at"] = _today(conn)
    cols = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    cur = conn.execute(
        f"INSERT INTO approval_requests ({cols}) VALUES ({marks})", tuple(fields.values())
    )
    row = conn.execute(
        "SELECT * FROM approval_requests WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return dict(row)


@mcp.tool()
def check_stock(sku: str, size: str, qty_requested: int = 1) -> dict[str, Any]:
    """Check whether an order for one SKU/size can be filled from on-hand stock.

    Reads `inventory` (and `pricing` for the list price). Returns the quantity
    on hand, shelf location, whether the requested quantity can be filled,
    the shortfall, and the on-hand quantity of the other sizes of the same SKU
    so the agent can offer an alternative.

    Args:
        sku: Product SKU, e.g. "CC-TEE-WHITE".
        size: Size code exactly as stored, e.g. "S", "M", "L", "XL", "OS".
        qty_requested: Units the customer wants (must be >= 1).
    """
    if qty_requested < 1:
        return _error("qty_requested must be at least 1.")

    with _connect() as conn:
        rows = conn.execute(
            "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ?",
            (sku,),
        ).fetchall()
        if not rows:
            return _error(f"No inventory records for SKU '{sku}'.")

        match = next((r for r in rows if r["size"] == size), None)
        if match is None:
            sizes = ", ".join(r["size"] for r in rows)
            return _error(f"SKU '{sku}' has no size '{size}'. Sizes on file: {sizes}.")

        price = conn.execute(
            "SELECT list_price FROM pricing WHERE sku = ?", (sku,)
        ).fetchone()

    on_hand = match["qty"]
    return {
        "sku": match["sku"],
        "name": match["name"],
        "size": match["size"],
        "location": match["location"],
        "qty_on_hand": on_hand,
        "qty_requested": qty_requested,
        "can_fulfill": on_hand >= qty_requested,
        "shortfall": max(qty_requested - on_hand, 0),
        "list_price": price["list_price"] if price else None,
        "other_sizes": [
            {"size": r["size"], "qty_on_hand": r["qty"]}
            for r in rows
            if r["size"] != size
        ],
    }


@mcp.tool()
def verify_rent_due(lease_id: int) -> dict[str, Any]:
    """Verify a rent notice against the lease on file and the cash available to pay it.

    Reads `leases` (rent amount, landlord, next due date), `desk` (today's
    business date) and `cash_accounts` (balances). Returns the lease terms,
    days until rent is due, each cash account's balance, and the balance that
    would remain after paying one month's rent from it.

    Args:
        lease_id: The lease id referenced by the ticket (tickets.lease_id).
    """
    with _connect() as conn:
        lease = conn.execute(
            "SELECT id, space_name, landlord, monthly_rent, next_due, notes "
            "FROM leases WHERE id = ?",
            (lease_id,),
        ).fetchone()
        if lease is None:
            return _error(f"No lease with id {lease_id}.")

        desk = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
        if desk is None:
            return _error("The desk table has no business date.")

        days_until_due = conn.execute(
            "SELECT CAST(julianday(?) - julianday(?) AS INTEGER)",
            (lease["next_due"], desk["date_today"]),
        ).fetchone()[0]

        accounts = conn.execute(
            "SELECT name, balance, date FROM cash_accounts ORDER BY name"
        ).fetchall()

    rent = lease["monthly_rent"]
    return {
        "lease_id": lease["id"],
        "space_name": lease["space_name"],
        "landlord": lease["landlord"],
        "monthly_rent": rent,
        "next_due": lease["next_due"],
        "notes": lease["notes"],
        "today": desk["date_today"],
        "days_until_due": days_until_due,
        "cash_accounts": [
            {
                "name": a["name"],
                "balance": a["balance"],
                "as_of": a["date"],
                "can_cover_rent": a["balance"] >= rent,
                "balance_after_rent": round(a["balance"] - rent, 2),
            }
            for a in accounts
        ],
    }


@mcp.tool()
def quote_bulk_discount(
    sku: str, size: str, qty: int, discount_pct: float
) -> dict[str, Any]:
    """Price a bulk order at a proposed discount and show the margin and stock impact.

    Reads `pricing` (unit cost and list price) and `inventory` (on-hand qty for
    the size). Returns the discounted unit price, order total, per-unit and
    total margin, margin percentage, whether the discounted price is still
    above cost, and any stock shortfall for the requested quantity.

    Args:
        sku: Product SKU, e.g. "CC-HOOD-NAVY".
        size: Size code exactly as stored, e.g. "M".
        qty: Units in the bulk order (must be >= 1).
        discount_pct: Proposed discount off list price, 0-100 (e.g. 15 for 15%).
    """
    if qty < 1:
        return _error("qty must be at least 1.")
    if not 0 <= discount_pct <= 100:
        return _error("discount_pct must be between 0 and 100.")

    with _connect() as conn:
        price = conn.execute(
            "SELECT sku, unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)
        ).fetchone()
        if price is None:
            return _error(f"No pricing record for SKU '{sku}'.")

        stock = conn.execute(
            "SELECT name, qty FROM inventory WHERE sku = ? AND size = ?", (sku, size)
        ).fetchone()
        if stock is None:
            return _error(f"No inventory record for SKU '{sku}' size '{size}'.")

    cost = price["unit_cost"]
    list_price = price["list_price"]
    unit_price = round(list_price * (1 - discount_pct / 100), 2)
    unit_margin = round(unit_price - cost, 2)
    return {
        "sku": price["sku"],
        "name": stock["name"],
        "size": size,
        "qty": qty,
        "unit_cost": cost,
        "list_price": list_price,
        "discount_pct": discount_pct,
        "discounted_unit_price": unit_price,
        "order_total": round(unit_price * qty, 2),
        "unit_margin": unit_margin,
        "total_margin": round(unit_margin * qty, 2),
        "margin_pct": round(unit_margin / unit_price * 100, 1) if unit_price else None,
        "above_cost": unit_price > cost,
        "qty_on_hand": stock["qty"],
        "shortfall": max(qty - stock["qty"], 0),
    }


@mcp.tool()
def get_ticket(ticket_id: int) -> dict[str, Any]:
    """Fetch one desk ticket with today's business date.

    Reads `tickets` and `desk`. Returns every ticket field (type, requester,
    subject, sku, size, qty, lease_id, invoice_id, status, notes, created_at)
    plus `today`, the business date every agent must use to judge due dates.

    Args:
        ticket_id: The ticket id, e.g. 101.
    """
    with _connect() as conn:
        ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if ticket is None:
            return _error(f"No ticket with id {ticket_id}.")
        return {**dict(ticket), "today": _today(conn)}


@mcp.tool()
def list_open_tickets() -> dict[str, Any]:
    """List every ticket that is not yet resolved.

    Reads `tickets` and `desk`. Returns id, type, requester, subject and status
    for each unresolved ticket, plus today's business date.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, type, requester, subject, status FROM tickets "
            "WHERE status <> 'resolved' ORDER BY id"
        ).fetchall()
        return {"today": _today(conn), "tickets": [dict(r) for r in rows]}


@mcp.tool()
def check_invoice(invoice_id: int) -> dict[str, Any]:
    """Check a vendor invoice: who it's from, whether it's paid, and whether it's overdue.

    Reads `invoices`, `vendors`, `desk`, `payments`, `approval_requests` and
    `tickets`. Overdue is judged against desk.date_today, never the wall clock.
    `is_paid` is true only if the invoice status is 'paid' or posted payments
    cover the full amount. Also lists tickets that reference the invoice and
    any payment already waiting for human approval.

    Args:
        invoice_id: The invoice id, e.g. tickets.invoice_id.
    """
    with _connect() as conn:
        inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if inv is None:
            return _error(f"No invoice with id {invoice_id}.")
        vendor = conn.execute(
            "SELECT id, name, specialty, lead_days FROM vendors WHERE id = ?",
            (inv["vendor_id"],),
        ).fetchone()
        today = _today(conn)
        payments = conn.execute(
            "SELECT * FROM payments WHERE kind = 'invoice' AND ref_id = ? ORDER BY id",
            (invoice_id,),
        ).fetchall()
        pending = _pending_request(conn, "invoice", invoice_id)
        tickets = conn.execute(
            "SELECT id, type, requester, status FROM tickets WHERE invoice_id = ?",
            (invoice_id,),
        ).fetchall()
        days_past_due = _days_between(conn, today, inv["due_date"])

    paid_total = round(sum(p["amount"] for p in payments), 2)
    is_paid = inv["status"] == "paid" or paid_total >= inv["amount"]
    return {
        "invoice_id": inv["id"],
        "amount": inv["amount"],
        "due_date": inv["due_date"],
        "status": inv["status"],
        "description": inv["description"],
        "vendor": dict(vendor) if vendor else None,
        "today": today,
        "is_paid": is_paid,
        "amount_paid": paid_total,
        "balance_owed": round(max(inv["amount"] - paid_total, 0), 2),
        "is_overdue": not is_paid and days_past_due > 0,
        "days_overdue": max(days_past_due, 0) if not is_paid else 0,
        "payments": [dict(p) for p in payments],
        "pending_approval_request": dict(pending) if pending else None,
        "linked_tickets": [dict(t) for t in tickets],
    }


@mcp.tool()
def list_vendors(specialty: str | None = None) -> dict[str, Any]:
    """List suppliers, optionally filtered by specialty, with their lead times.

    Reads `vendors` and `desk`. For each vendor returns id, name, specialty,
    lead_days and the earliest arrival date if ordered today
    (desk.date_today + lead_days).

    Args:
        specialty: Optional case-insensitive text to match, e.g. "apparel".
    """
    with _connect() as conn:
        today = _today(conn)
        sql = (
            "SELECT id, name, specialty, lead_days, date(?, '+' || lead_days || ' days') "
            "AS earliest_arrival FROM vendors"
        )
        params: tuple[Any, ...] = (today,)
        if specialty:
            sql += " WHERE specialty LIKE ?"
            params += (f"%{specialty}%",)
        rows = conn.execute(sql + " ORDER BY id", params).fetchall()
    if not rows:
        return _error(f"No vendors match specialty '{specialty}'.")
    return {"today": today, "vendors": [dict(r) for r in rows]}


@mcp.tool()
def list_payments(kind: str | None = None, ref_id: int | None = None) -> dict[str, Any]:
    """List money that has actually been paid out (the `payments` audit log).

    Reads `payments`. Every row here was approved by a human (`approved_by`).
    Use this to confirm something was not already paid before preparing a
    payment. Pending, unapproved requests are NOT here; see
    list_approval_requests.

    Args:
        kind: Optional filter, e.g. "rent" or "invoice".
        ref_id: Optional filter on the referenced id (lease id or invoice id).
    """
    sql, params = "SELECT * FROM payments WHERE 1 = 1", []
    if kind is not None:
        sql += " AND kind = ?"
        params.append(kind)
    if ref_id is not None:
        sql += " AND ref_id = ?"
        params.append(ref_id)
    with _connect() as conn:
        rows = conn.execute(sql + " ORDER BY id", params).fetchall()
    return {"count": len(rows), "payments": [dict(r) for r in rows]}


@mcp.tool()
def list_approval_requests(
    ticket_id: int | None = None, status: str | None = "pending"
) -> dict[str, Any]:
    """List payments, purchase orders and price overrides prepared by agents.

    Reads `approval_requests`. These are proposals waiting for (or decided by)
    a human; no cash has moved for a 'pending' request.

    Args:
        ticket_id: Optional filter to one ticket.
        status: Filter by status (default "pending"); pass null for all.
    """
    sql, params = "SELECT * FROM approval_requests WHERE 1 = 1", []
    if ticket_id is not None:
        sql += " AND ticket_id = ?"
        params.append(ticket_id)
    if status is not None:
        sql += " AND status = ?"
        params.append(status)
    with _connect() as conn:
        rows = conn.execute(sql + " ORDER BY id", params).fetchall()
    return {"count": len(rows), "requests": [dict(r) for r in rows]}


@mcp.tool()
def prepare_payment(
    ticket_id: int,
    kind: str,
    ref_id: int,
    requested_by: str,
    reason: str,
    account: str = "checking",
) -> dict[str, Any]:
    """Prepare (NOT make) a rent or invoice payment for human approval.

    Reads `tickets`, `leases` or `invoices`/`vendors`, `cash_accounts`,
    `payments`, `approval_requests`; writes one 'pending' row to
    `approval_requests`. Never writes to `payments` and never changes a cash
    balance: a human must approve before cash moves.

    The amount is taken from the database (lease monthly_rent or invoice
    amount), never from the caller. Refuses if: the amount exceeds the
    per-request spend cap, the invoice is not open, a pending request already
    exists for the same item, or the account can't cover this amount on top of
    other pending requests on that account.

    Args:
        ticket_id: Ticket this payment belongs to.
        kind: "rent" (ref_id = lease id) or "invoice" (ref_id = invoice id).
        ref_id: The lease id or invoice id.
        requested_by: Agent preparing it: boss, inventory, accounting, facilities or customer_service.
        reason: One sentence on why this should be paid, citing the facts checked.
        account: Cash account to pay from (default "checking").
    """
    if err := _check_requester(requested_by):
        return _error(err)
    if kind not in {"rent", "invoice"}:
        return _error("kind must be 'rent' or 'invoice'.")

    with _connect() as conn:
        if not _ticket_exists(conn, ticket_id):
            return _error(f"No ticket with id {ticket_id}.")

        if kind == "rent":
            lease = conn.execute("SELECT * FROM leases WHERE id = ?", (ref_id,)).fetchone()
            if lease is None:
                return _error(f"No lease with id {ref_id}.")
            amount, payee, due = lease["monthly_rent"], lease["landlord"], lease["next_due"]
            what = f"rent for {lease['space_name']}"
        else:
            inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (ref_id,)).fetchone()
            if inv is None:
                return _error(f"No invoice with id {ref_id}.")
            if inv["status"] != "open":
                return _error(f"Invoice {ref_id} has status '{inv['status']}', not 'open'.")
            vendor = conn.execute(
                "SELECT name FROM vendors WHERE id = ?", (inv["vendor_id"],)
            ).fetchone()
            amount, due = inv["amount"], inv["due_date"]
            payee = vendor["name"] if vendor else f"vendor {inv['vendor_id']}"
            what = f"invoice {ref_id} ({inv['description']})"

        if amount > SPEND_CAP_PER_REQUEST:
            return _error(
                f"${amount:,.2f} exceeds the ${SPEND_CAP_PER_REQUEST:,.2f} per-request "
                "spend cap. Escalate to the owner."
            )
        if existing := _pending_request(conn, kind, ref_id):
            return _error(
                f"Approval request {existing['id']} for this {kind} is already pending."
            )

        acct = conn.execute(
            "SELECT name, balance FROM cash_accounts WHERE name = ?", (account,)
        ).fetchone()
        if acct is None:
            return _error(f"No cash account named '{account}'.")
        already_pending = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM approval_requests "
            "WHERE account = ? AND status = 'pending'",
            (account,),
        ).fetchone()[0]
        balance_if_all_approved = round(acct["balance"] - already_pending - amount, 2)
        if balance_if_all_approved < 0:
            return _error(
                f"'{account}' has ${acct['balance']:,.2f} with ${already_pending:,.2f} "
                f"already pending; it can't also cover ${amount:,.2f}."
            )

        request = _insert_request(
            conn,
            ticket_id=ticket_id,
            kind=kind,
            ref_id=ref_id,
            amount=amount,
            account=account,
            details=f"Pay {payee} ${amount:,.2f} for {what}, due {due}. Reason: {reason}",
            requested_by=requested_by,
        )

    return {
        "approval_request": request,
        "cash_moved": False,
        "next_step": "A human must approve this request before any payment is recorded.",
        "payee": payee,
        "due": due,
        "account_balance_now": acct["balance"],
        "other_pending_on_account": already_pending,
        "balance_if_all_pending_approved": balance_if_all_approved,
    }


@mcp.tool()
def prepare_purchase_order(
    ticket_id: int,
    vendor_id: int,
    sku: str,
    size: str,
    qty: int,
    requested_by: str,
    reason: str,
) -> dict[str, Any]:
    """Prepare (NOT place) a restock purchase order for human approval.

    Reads `tickets`, `vendors`, `pricing`, `inventory`, `desk`,
    `approval_requests`; writes one 'pending' row to `approval_requests`.
    Estimated cost = pricing.unit_cost x qty. Expected arrival =
    desk.date_today + vendor lead_days. Refuses if the cost exceeds the
    per-request spend cap or the same SKU/size already has a pending order for
    this ticket. The PO is charged to checking on approval, so it counts toward
    checking's pending total; `cash_warning` is set if checking can't cover
    every pending request.

    Args:
        ticket_id: Ticket this restock is for.
        vendor_id: Supplier id from list_vendors.
        sku: Product SKU to restock.
        size: Size code exactly as stored.
        qty: Units to order (must be >= 1).
        requested_by: Agent preparing it: boss, inventory, accounting, facilities or customer_service.
        reason: One sentence on why the restock is needed, citing the stock check.
    """
    if err := _check_requester(requested_by):
        return _error(err)
    if qty < 1:
        return _error("qty must be at least 1.")

    with _connect() as conn:
        if not _ticket_exists(conn, ticket_id):
            return _error(f"No ticket with id {ticket_id}.")
        vendor = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
        if vendor is None:
            return _error(f"No vendor with id {vendor_id}.")
        price = conn.execute("SELECT unit_cost FROM pricing WHERE sku = ?", (sku,)).fetchone()
        if price is None:
            return _error(f"No pricing record for SKU '{sku}'.")
        stock = conn.execute(
            "SELECT qty FROM inventory WHERE sku = ? AND size = ?", (sku, size)
        ).fetchone()
        if stock is None:
            return _error(f"No inventory record for SKU '{sku}' size '{size}'.")

        cost = round(price["unit_cost"] * qty, 2)
        if cost > SPEND_CAP_PER_REQUEST:
            return _error(
                f"Estimated cost ${cost:,.2f} exceeds the ${SPEND_CAP_PER_REQUEST:,.2f} "
                "per-request spend cap. Escalate to the owner."
            )
        existing = conn.execute(
            "SELECT id FROM approval_requests WHERE kind = 'purchase_order' AND status = 'pending' "
            "AND ticket_id = ? AND sku = ? AND size = ?",
            (ticket_id, sku, size),
        ).fetchone()
        if existing:
            return _error(
                f"Purchase order request {existing['id']} for {sku} {size} is already pending."
            )
        today = _today(conn)
        arrival = conn.execute(
            "SELECT date(?, '+' || ? || ' days')", (today, vendor["lead_days"])
        ).fetchone()[0]
        # On approval the vendor is paid from checking, so count it against checking.
        balance, already_pending = conn.execute(
            "SELECT balance, (SELECT COALESCE(SUM(amount), 0) FROM approval_requests "
            "WHERE account = 'checking' AND status = 'pending') FROM cash_accounts "
            "WHERE name = 'checking'"
        ).fetchone()
        balance_if_all_approved = round(balance - already_pending - cost, 2)

        request = _insert_request(
            conn,
            ticket_id=ticket_id,
            kind="purchase_order",
            vendor_id=vendor_id,
            sku=sku,
            size=size,
            qty=qty,
            amount=cost,
            account="checking",
            details=(
                f"Order {qty} x {sku} {size} from {vendor['name']} at "
                f"${price['unit_cost']:,.2f}/unit; arrives about {arrival} if approved "
                f"today. Reason: {reason}"
            ),
            requested_by=requested_by,
        )

    return {
        "approval_request": request,
        "order_placed": False,
        "next_step": "A human must approve this purchase order before it is sent.",
        "vendor": vendor["name"],
        "lead_days": vendor["lead_days"],
        "expected_arrival_if_approved_today": arrival,
        "qty_on_hand_now": stock["qty"],
        "checking_balance_now": balance,
        "balance_if_all_pending_approved": balance_if_all_approved,
        "cash_warning": (
            "Checking can't cover every pending request; the approver must choose."
            if balance_if_all_approved < 0
            else None
        ),
    }


@mcp.tool()
def prepare_price_override(
    ticket_id: int,
    sku: str,
    size: str,
    qty: int,
    discount_pct: float,
    requested_by: str,
    reason: str,
) -> dict[str, Any]:
    """Prepare (NOT grant) a discounted price for human approval.

    Reads `tickets`, `pricing`, `inventory`, `approval_requests`; writes one
    'pending' row to `approval_requests`. Refuses discounts above the maximum
    allowed discount or that would leave less than the minimum margin, and
    refuses if this ticket already has a pending price override.

    Args:
        ticket_id: Ticket asking for the discount.
        sku: Product SKU.
        size: Size code exactly as stored.
        qty: Units in the order (must be >= 1).
        discount_pct: Proposed discount off list price, e.g. 15 for 15%.
        requested_by: Agent preparing it: boss, inventory, accounting, facilities or customer_service.
        reason: One sentence justifying the discount, citing the margin check.
    """
    if err := _check_requester(requested_by):
        return _error(err)
    if qty < 1:
        return _error("qty must be at least 1.")
    if not 0 < discount_pct <= MAX_DISCOUNT_PCT:
        return _error(f"discount_pct must be above 0 and at most {MAX_DISCOUNT_PCT}.")

    with _connect() as conn:
        if not _ticket_exists(conn, ticket_id):
            return _error(f"No ticket with id {ticket_id}.")
        price = conn.execute(
            "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)
        ).fetchone()
        if price is None:
            return _error(f"No pricing record for SKU '{sku}'.")
        stock = conn.execute(
            "SELECT qty FROM inventory WHERE sku = ? AND size = ?", (sku, size)
        ).fetchone()
        if stock is None:
            return _error(f"No inventory record for SKU '{sku}' size '{size}'.")

        unit_price = round(price["list_price"] * (1 - discount_pct / 100), 2)
        margin_pct = round((unit_price - price["unit_cost"]) / unit_price * 100, 1)
        if margin_pct < MIN_MARGIN_PCT:
            return _error(
                f"{discount_pct}% off leaves a {margin_pct}% margin, below the "
                f"{MIN_MARGIN_PCT}% minimum."
            )
        if existing := _pending_request(conn, "price_override", ticket_id):
            return _error(
                f"Price override request {existing['id']} for ticket {ticket_id} is already pending."
            )

        total = round(unit_price * qty, 2)
        request = _insert_request(
            conn,
            ticket_id=ticket_id,
            kind="price_override",
            ref_id=ticket_id,
            sku=sku,
            size=size,
            qty=qty,
            amount=total,
            details=(
                f"{discount_pct}% off {qty} x {sku} {size}: ${unit_price:,.2f}/unit "
                f"(list ${price['list_price']:,.2f}), total ${total:,.2f}, margin "
                f"{margin_pct}%. Reason: {reason}"
            ),
            requested_by=requested_by,
        )

    return {
        "approval_request": request,
        "price_granted": False,
        "next_step": "A human must approve this discount before it is quoted as final.",
        "discounted_unit_price": unit_price,
        "order_total": total,
        "margin_pct": margin_pct,
        "qty_on_hand": stock["qty"],
        "shortfall": max(qty - stock["qty"], 0),
    }


@mcp.tool()
def update_ticket_status(
    ticket_id: int, status: str, note: str, updated_by: str
) -> dict[str, Any]:
    """Change a ticket's status and append a dated note to its history.

    Reads `tickets`, `desk`, `approval_requests`; writes `tickets.status` and
    `tickets.notes`. Existing notes are kept; the new note is appended as
    "[date_today agent] note". A ticket can't be marked 'resolved' while it
    still has a pending approval request.

    Args:
        ticket_id: Ticket to update.
        status: One of open, in_progress, waiting_on_approval,
            waiting_on_customer, waiting_on_vendor, resolved.
        note: Short factual note on what was done or what is being waited on.
        updated_by: Agent making the change: boss, inventory, accounting, facilities or customer_service.
    """
    if err := _check_requester(updated_by):
        return _error(err)
    if status not in TICKET_STATUSES:
        return _error(f"status must be one of: {', '.join(sorted(TICKET_STATUSES))}.")

    with _connect() as conn:
        ticket = conn.execute(
            "SELECT status, notes FROM tickets WHERE id = ?", (ticket_id,)
        ).fetchone()
        if ticket is None:
            return _error(f"No ticket with id {ticket_id}.")
        if status == "resolved":
            pending = conn.execute(
                "SELECT COUNT(*) FROM approval_requests WHERE ticket_id = ? AND status = 'pending'",
                (ticket_id,),
            ).fetchone()[0]
            if pending:
                return _error(
                    f"Ticket {ticket_id} has {pending} pending approval request(s); "
                    "use 'waiting_on_approval' instead."
                )
        entry = f"[{_today(conn)} {updated_by}] {note}"
        notes = f"{ticket['notes']}\n{entry}" if ticket["notes"] else entry
        conn.execute(
            "UPDATE tickets SET status = ?, notes = ? WHERE id = ?", (status, notes, ticket_id)
        )

    return {
        "ticket_id": ticket_id,
        "old_status": ticket["status"],
        "new_status": status,
        "notes": notes,
    }


if __name__ == "__main__":
    mcp.run()
