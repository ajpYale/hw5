# Campus Customs MCP Server

An MCP server, built with FastMCP, that gives the Campus Customs agents database-backed tools for working the desk tickets (101, 102, 103). It's the agents' **only** source of shop data: the backend has no direct-DB tools.

## Database

- **File:** `data/campus_customs_new.db`, the working copy of `data/campus_customs.db`. The original is never touched.
- **Path:** resolved relative to the project root (`Path(__file__).resolve().parents[1] / "data" / ...`), so the server works no matter which folder it's launched from. For tests, the `CAMPUS_CUSTOMS_DB` env var can point it at a scratch copy instead.
- **Mode:** opened read/write (`mode=rw`). If the file is missing, the server raises an error instead of silently creating an empty database.
- **No made-up data:** every value a tool returns is read from (or computed directly from) the database. Unknown ids, SKUs or sizes return `{"error": "..."}`.
- **New table, `approval_requests`:** created on first connection (`CREATE TABLE IF NOT EXISTS`). The `prepare_*` tools write *pending* requests here. `payments` is never written by any tool, because its `paid_at` and `approved_by` columns are NOT NULL, so a row there means a human already approved it and cash moved. Approval happens only through the API (`POST /approvals/{id}/approve` in `backend/main.py`), which fills in `decided_by`/`decided_at` and moves the cash.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER | PRIMARY KEY |
| ticket_id | INTEGER | NOT NULL, FK → tickets(id) |
| kind | TEXT | `rent`, `invoice`, `purchase_order` or `price_override` |
| ref_id | INTEGER | lease id, invoice id, or ticket id (for price overrides) |
| vendor_id | INTEGER | FK → vendors(id), purchase orders only |
| sku, size, qty | TEXT/TEXT/INTEGER | purchase orders and price overrides |
| amount | REAL | NOT NULL, always computed from the DB |
| account | TEXT | cash account charged on approval (`checking` for payments and POs) |
| details | TEXT | human-readable summary plus the agent's reason |
| requested_by | TEXT | NOT NULL, agent name |
| status | TEXT | NOT NULL, default `pending`; `approved` after a human approves |
| created_at | TEXT | NOT NULL, `desk.date_today` |
| decided_by | TEXT | the human who approved (set by the API) |
| decided_at | TEXT | when they approved (UTC timestamp, set by the API) |

## Server-side guardrails

These are enforced in the tools, so no prompt can talk past them:

| Rule | Value |
|---|---|
| Max amount per prepared payment or purchase order | $2,500 |
| Max discount an agent can propose | 25% |
| Min margin after discount | 30% |
| Payment amount | taken from the lease or invoice, never from the agent |
| Cash check | a payment is refused if the account can't cover it plus everything already pending on that account. A PO is still prepared but returns `cash_warning` (the approver decides) |
| Duplicates | refused if the same rent, invoice, PO or price override is already pending |
| Invoice payments | only for invoices with status `open` |
| `requested_by` / `updated_by` | must be one of the five agent names |
| Ticket status | only from a fixed list; can't become `resolved` while it has a pending approval request |

## Tools

### Read-only

| Tool | Reads | Returns | Tickets |
|---|---|---|---|
| `get_ticket(ticket_id)` | tickets, desk | all ticket fields + `today` | all |
| `list_open_tickets()` | tickets, desk | every unresolved ticket + `today` | all |
| `check_stock(sku, size, qty_requested=1)` | inventory, pricing | on hand, location, can_fulfill, shortfall, list price, other sizes | 101, 103 |
| `verify_rent_due(lease_id)` | leases, desk, cash_accounts | lease terms, days until due, balances and balance after rent | 102 |
| `quote_bulk_discount(sku, size, qty, discount_pct)` | pricing, inventory | discounted price, total, unit/total margin, margin %, above_cost, shortfall | 103 |
| `check_invoice(invoice_id)` | invoices, vendors, desk, payments, approval_requests, tickets | amount, vendor, `is_paid`, `is_overdue`, `days_overdue` vs. `today`, payments, pending request, linked tickets | 101 |
| `list_vendors(specialty=None)` | vendors, desk | id, name, specialty, lead_days, earliest arrival if ordered today | 101, 103 |
| `list_payments(kind=None, ref_id=None)` | payments | money actually paid out | 101, 102 |
| `list_approval_requests(ticket_id=None, status="pending")` | approval_requests | prepared requests and their status | all |

### Write (prepare only, or ticket status)

| Tool | Reads | Writes | Tickets |
|---|---|---|---|
| `prepare_payment(ticket_id, kind, ref_id, requested_by, reason, account="checking")` | tickets, leases or invoices + vendors, cash_accounts, approval_requests | approval_requests (pending) | 101 (invoice 501), 102 (rent) |
| `prepare_purchase_order(ticket_id, vendor_id, sku, size, qty, requested_by, reason)` | tickets, vendors, pricing, inventory, desk, approval_requests | approval_requests (pending) | 103 (12 × hoodie M) |
| `prepare_price_override(ticket_id, sku, size, qty, discount_pct, requested_by, reason)` | tickets, pricing, inventory, approval_requests | approval_requests (pending) | 103 |
| `update_ticket_status(ticket_id, status, note, updated_by)` | tickets, desk, approval_requests | tickets.status, tickets.notes (appends, never replaces) | all |

## Setup

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
```

`mcp` is pinned below 2.0 because mcp 2.x renamed `FastMCP` to `MCPServer`.

## Running

The server runs over stdio and is launched by its clients; you don't start it by hand:

- **Claude Code:** registered in `.mcp.json` at the project root.
- **Agent team:** `backend/mcp_toolset.py` launches it with the venv's Python, and all five agents share one server process per ticket.

To start it manually for debugging:

```bash
.venv/Scripts/python mcp_server/server.py
```
