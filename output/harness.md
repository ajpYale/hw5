# Harness

The Campus Customs desk is a small shop run by five AI agents and one human. Tickets come in. The **Boss** agent routes each one to the specialists it needs. Every agent gets its facts only through the **campus-customs MCP server**. Agents can *prepare* payments, restock orders and discounts, but only a **human clicking Approve on the dashboard** moves cash.

```
React dashboard (frontend/, :5173)
        │  polls /tickets /events /approvals /cash; POST run / approve / reset
        ▼
FastAPI (backend/main.py, :8000) ── approve route: the ONLY cash-moving code (backend/shop_db.py)
        │  starts a ticket run in the background
        ▼
Agent team (PydanticAI, gpt-6-luna via Portkey): Boss → Inventory / Accounting / Facilities / Customer Service
        │  every fact through MCP (stdio), every loop step → output/audit_trail.json
        ▼
MCP server (mcp_server/server.py) ── data/campus_customs_new.db (working copy of data/campus_customs.db)
```

**Contents:** [Database](#database) · [Agents](#agents) · [MCP Tools](#mcp-tools) · [Safety](#safety) · [API Routes](#api-routes) · [Dashboard](#dashboard) · [Run results](#run-results)

## Database

Source: `data/campus_customs.db` (original, read-only). Working copy: `data/campus_customs_new.db`. All homework changes go to the working copy, and `POST /reset` copies the original back over it.

The original DB has 9 tables and no views or triggers. The MCP server adds a 10th table to the working copy, `approval_requests` (described below), for prepared payments, POs and price overrides. Field types and constraints below come straight from the `CREATE TABLE` statements. Row counts are for the original DB.

### desk (1 row)

| Field | Type | Constraints |
|---|---|---|
| date_today | TEXT | NOT NULL |
| notes | TEXT | |

**Why it matters:** gives the agents the current business date (`2026-08-31`), which they need to judge due dates and deadlines.

### tickets (3 rows)

| Field | Type | Constraints |
|---|---|---|
| id | INTEGER | PRIMARY KEY |
| type | TEXT | NOT NULL |
| requester | TEXT | NOT NULL |
| subject | TEXT | NOT NULL |
| sku | TEXT | |
| size | TEXT | |
| qty | INTEGER | |
| lease_id | INTEGER | FK → leases(id) |
| invoice_id | INTEGER | FK → invoices(id) |
| status | TEXT | NOT NULL |
| notes | TEXT | |
| created_at | TEXT | NOT NULL |

**Why it matters:** the agents' work queue. Each open ticket is a task, and its `type` decides which agent and tools handle it.

### inventory (10 rows)

| Field | Type | Constraints |
|---|---|---|
| sku | TEXT | NOT NULL, PRIMARY KEY (sku, size) |
| name | TEXT | NOT NULL |
| size | TEXT | NOT NULL, PRIMARY KEY (sku, size) |
| qty | INTEGER | NOT NULL |
| location | TEXT | NOT NULL |

**Why it matters:** shows on-hand stock per SKU and size, so the agents can check whether an order can be filled now or needs a reprint.

### pricing (4 rows)

| Field | Type | Constraints |
|---|---|---|
| sku | TEXT | PRIMARY KEY |
| unit_cost | REAL | NOT NULL |
| list_price | REAL | NOT NULL |

**Why it matters:** gives cost and list price per SKU, so the agents can quote prices and check that a discount still leaves a margin.

### vendors (3 rows)

| Field | Type | Constraints |
|---|---|---|
| id | INTEGER | PRIMARY KEY |
| name | TEXT | NOT NULL |
| specialty | TEXT | NOT NULL |
| lead_days | INTEGER | NOT NULL |

**Why it matters:** shows who can resupply what and how fast. `lead_days` sets realistic delivery promises.

### leases (1 row)

| Field | Type | Constraints |
|---|---|---|
| id | INTEGER | PRIMARY KEY |
| space_name | TEXT | NOT NULL |
| landlord | TEXT | NOT NULL |
| monthly_rent | REAL | NOT NULL |
| next_due | TEXT | NOT NULL |
| notes | TEXT | |

**Why it matters:** holds the rent obligation (amount, landlord, next due date) that the agents must verify before paying a rent notice.

### cash_accounts (1 row)

| Field | Type | Constraints |
|---|---|---|
| name | TEXT | PRIMARY KEY |
| balance | REAL | NOT NULL |
| date | TEXT | NOT NULL |

**Why it matters:** shows available cash (`checking` = $3,400 as of 2026-08-31), which limits what the agents can pay.

### payments (0 rows)

| Field | Type | Constraints |
|---|---|---|
| id | INTEGER | PRIMARY KEY |
| kind | TEXT | NOT NULL |
| ref_id | INTEGER | (no declared FK) |
| amount | REAL | NOT NULL |
| account | TEXT | NOT NULL |
| paid_at | TEXT | NOT NULL |
| approved_by | TEXT | NOT NULL |

**Why it matters:** the audit log where the agents record any money they pay out. `approved_by` is required, so every payment needs a named approver.

### invoices (1 row)

| Field | Type | Constraints |
|---|---|---|
| id | INTEGER | PRIMARY KEY |
| vendor_id | INTEGER | NOT NULL, FK → vendors(id) |
| amount | REAL | NOT NULL |
| due_date | TEXT | NOT NULL |
| status | TEXT | NOT NULL |
| description | TEXT | |

**Why it matters:** lists vendor bills owed. The agents need these to settle payables and to see which supplier work is already in progress.

### approval_requests (added by the MCP server; 0 rows after reset)

| Field | Type | Constraints |
|---|---|---|
| id | INTEGER | PRIMARY KEY |
| ticket_id | INTEGER | NOT NULL, FK → tickets(id) |
| kind | TEXT | NOT NULL (`rent`, `invoice`, `purchase_order`, `price_override`) |
| ref_id | INTEGER | lease id, invoice id, or ticket id for price overrides |
| vendor_id | INTEGER | FK → vendors(id), purchase orders only |
| sku / size / qty | TEXT / TEXT / INTEGER | purchase orders and price overrides |
| amount | REAL | NOT NULL, always computed from the DB |
| account | TEXT | cash account charged on approval (`checking`) |
| details | TEXT | summary plus the agent's reason |
| requested_by | TEXT | NOT NULL, agent name |
| status | TEXT | NOT NULL, `pending` → `approved` |
| created_at | TEXT | NOT NULL, `desk.date_today` |
| decided_by / decided_at | TEXT / TEXT | the human approver and when (set by the API) |

**Why it matters:** this is where the human-approval gate lives. Agents write *pending* rows here. Only `POST /approvals/{id}/approve` turns one into a `payments` row and a lower checking balance.

### Relationships

- **Declared foreign keys:**
  - `tickets.lease_id → leases.id`
  - `tickets.invoice_id → invoices.id`
  - `invoices.vendor_id → vendors.id`
  - `approval_requests.ticket_id → tickets.id`, `approval_requests.vendor_id → vendors.id`
- **Implicit links (matching values, no FK constraint):**
  - `tickets.(sku, size) → inventory.(sku, size)`
  - `tickets.sku / inventory.sku → pricing.sku`
  - `payments.ref_id` is a generic reference whose meaning depends on `kind`
  - `payments.account → cash_accounts.name`

### Open tickets

Business date is 2026-08-31.

| Ticket | Type / requester | Request | Tables touched |
|---|---|---|---|
| **101** | customer_order, Tauhid Zaman | 1 × CC-TEE-WHITE (Classic Bulldog Tee), size S | inventory, pricing, invoices, vendors |
| **102** | rent_notice, Elm City Properties | "Shop rent due in 2 days" | leases, cash_accounts, payments |
| **103** | price_override, Yale AI Club | 20 × CC-HOOD-NAVY (Basic Hoodie Big Yale), size M, bulk discount | inventory, pricing, vendors |

- **101**
  - **Stock:** inventory shows size S at **qty 0**, so the order can't be filled from stock. List price is $28 and unit cost is $8.
  - **Invoice link:** `invoice_id` points to invoice **501**. That's a $840 bill from vendor 1, Bulldog Print Co (apparel reprint, 5 lead days), described as "Rush reprint CC-TEE-WHITE S".
  - **Overdue:** the invoice was due 2026-08-28 and its status is still `open`, so it's 3 days overdue.
- **102**
  - **Lease:** `lease_id` points to lease **1**, the Chapel Street shop, landlord Elm City Properties, $2,400/month, next due 2026-09-02. That matches "due in 2 days".
  - **Cash:** paying it would draw on `cash_accounts` (checking, $3,400) and add a row to `payments`.
  - **Combined cash need:** paying both this rent and invoice 501 would take $3,240, leaving $160.
- **103**
  - **Stock:** inventory has **8** size M hoodies against 20 requested, so it's 12 short.
  - **Pricing:** list price is $58 and unit cost is $22, so any discount needs a margin check.
  - **Restock:** no FK links this ticket to anything. Restocking would fall to vendor 1, Bulldog Print Co (apparel reprint, 5 lead days).

## Agents

Five PydanticAI agents live in `backend/`. All of them use `gpt-6-luna` through Portkey (`PORTKEY_API_KEY` from the root `.env`); no other model is configured. Shared types are in `backend/models.py`, there's one file per role in `backend/agents/`, and one system prompt per role in `backend/prompts/`. Run a ticket with `.venv/Scripts/python -m backend.run_ticket 101`.

| Agent | Job | MCP tools it can call | Output |
|---|---|---|---|
| **Boss** | Receives every ticket, picks who works it first, coordinates hand-offs, sets the final ticket status. Does no specialist work itself. | get_ticket, list_open_tickets, list_approval_requests, update_ticket_status | `TicketResolution` |
| **Inventory** | Stock on hand, other sizes, suppliers and lead times. Prepares restock purchase orders (checks first that a reprint isn't already underway). | get_ticket, check_stock, quote_bulk_discount, list_vendors, list_approval_requests, prepare_purchase_order | `SpecialistReport` |
| **Accounting** | Vendor invoices (paid? overdue vs. `desk.date_today`?), payments, cash, discount margins. Prepares rent/invoice payments and price overrides. | get_ticket, check_invoice, list_payments, list_approval_requests, verify_rent_due, quote_bulk_discount, prepare_payment, prepare_price_override | `SpecialistReport` |
| **Facilities** | Verifies rent notices against the lease on file (sender, amount, due date) and flags mismatches as possible fraud. Read-only: hands verified rent to Accounting. | get_ticket, verify_rent_due, list_payments, list_approval_requests | `SpecialistReport` |
| **Customer Service** | Drafts the customer reply: what's available, alternatives, estimates and pending-approval wording. Never mentions internal facts. Read-only. | get_ticket, check_stock, list_approval_requests | `SpecialistReport` |

**Connectivity:** every agent also has a `delegate(agent, request)` tool and can hand off to any other agent, including back to the Boss. A delegation runs the target agent and returns its report as the tool result. Default first hops set by the Boss: 101 → Inventory, 102 → Facilities, 103 → Accounting.

**Audit:** every agent-loop step (one model response plus the tools it called) is appended to `output/audit_trail.json`. Each record has a timestamp, session id, ticket id, agent, depth, who delegated, step number, input, tool calls with args and results, delegation targets, output, step token usage, and running ticket token usage. Failed steps get an `error` record. The file is a JSON array that only ever grows: each write re-reads it, appends, and atomically replaces it, and refuses to touch it if it isn't a valid array.

## MCP Tools

Server: `mcp_server/server.py` (FastMCP, server name `campus-customs`). It reads and writes `data/campus_customs_new.db`, located relative to the project root. Every value a tool returns comes from the DB, and a missing record returns `{"error": "..."}`. The agents get all shop facts through this server; there are no direct-DB tools in `backend/`.

The server adds one table to the working DB, `approval_requests`, where the `prepare_*` tools put pending requests. No tool ever writes to `payments`: its `paid_at` and `approved_by` are NOT NULL, so a row there means a human approved it and cash moved.

| Tool | Reads | Writes | Used by | Ticket |
|---|---|---|---|---|
| `get_ticket` | tickets, desk | none | all five | all |
| `list_open_tickets` | tickets, desk | none | Boss | all |
| `check_stock` | inventory, pricing | none | Inventory, Customer Service | 101, 103 |
| `verify_rent_due` | leases, desk, cash_accounts | none | Facilities, Accounting | 102 |
| `quote_bulk_discount` | pricing, inventory | none | Accounting, Inventory | 103 |
| `check_invoice` | invoices, vendors, desk, payments, approval_requests, tickets | none | Accounting | 101 |
| `list_vendors` | vendors, desk | none | Inventory | 101, 103 |
| `list_payments` | payments | none | Accounting, Facilities | 101, 102 |
| `list_approval_requests` | approval_requests | none | all five | all |
| `prepare_payment` | tickets, leases / invoices + vendors, cash_accounts, approval_requests | approval_requests | Accounting | 101, 102 |
| `prepare_purchase_order` | tickets, vendors, pricing, inventory, desk, approval_requests | approval_requests | Inventory | 103 |
| `prepare_price_override` | tickets, pricing, inventory, approval_requests | approval_requests | Accounting | 103 |
| `update_ticket_status` | tickets, desk, approval_requests | tickets (status, notes) | Boss | all |

Why the original three are the right tools for their tickets:

- **`check_stock` → 101.** Tauhid wants a size S Classic Bulldog Tee, which shows **0 on hand**. The tool confirms the stockout before anyone promises the order, and lists the other sizes still in stock (M: 5, L: 3, XL: 2) so the agent can offer an alternative or explain a wait.
- **`verify_rent_due` → 102.** The rent notice arrived as an email. The tool checks it against lease 1 ($2,400 to Elm City Properties, due 2026-09-02, 2 days after the desk date) and shows checking's $3,400 would drop to $1,000 if paid, so the agent can confirm the bill is real and affordable before any money moves.
- **`quote_bulk_discount` → 103.** The Yale AI Club wants a discount on 20 size M hoodies. The tool prices any proposed discount against the $22 unit cost (e.g. 15% off gives $49.30/unit and a 55.4% margin) and flags that only 8 are on hand, so the agent can't approve a price that loses money or a quantity it can't ship.

What the new tools add: `check_invoice` shows that 101's linked invoice 501 is unpaid and 3 days overdue, which blocks shipping. `prepare_payment` turns 101's invoice and 102's rent into requests waiting for approval. `list_vendors` and `prepare_purchase_order` cover 103's 12-unit shortfall (Bulldog Print Co, 5 days). `prepare_price_override` puts 103's discount up for approval. `update_ticket_status` records where each ticket stands.

## Safety

| Guardrail | How it's enforced |
|---|---|
| **Human approval for money** | Agents can only *prepare* payments, purchase orders and price overrides (`approval_requests`, status `pending`). No MCP tool writes `payments` or changes `cash_accounts`. Cash moves only when a named human calls `POST /approvals/{id}/approve`, which re-checks the amount and the balance first. Prompts forbid saying anything "was paid / ordered / approved". |
| **Spend caps** | Server-side: max **$2,500** per prepared payment or PO. A payment is refused if the account can't cover it plus everything already pending on that account. Payment amounts come from the lease or invoice, never from the agent. Duplicate pending requests are refused. Prompts forbid splitting requests to get under the cap. |
| **Discount floor** | Server-side: max **25%** discount and at least **30%** margin. Prompts treat 25% as a ceiling, not a target (10–15% is normal for ~20 units). |
| **No shipping on unpaid invoices** | There is no ship tool. `check_invoice` reports `is_paid`, and every prompt forbids promising shipment while a linked invoice is unpaid. |
| **Date discipline** | Overdue and due-soon are judged against `desk.date_today`, returned as `today` by the tools. The real calendar is never used. |
| **No invented data** | Every fact comes from an MCP tool. Agent reports carry a `facts` list tagged with the source tool. Missing records return errors, which agents must report as "not on file". |
| **No customer PII leakage** | Customer Service only gets customer-safe facts from the Boss, and its prompt bans vendor names, invoices, cost, margin, rent, cash and other customers. The DB holds only requester names, with no contact details, and agents can't email anyone. |
| **Fraud check on notices** | Facilities verifies an emailed rent notice against the lease on file and blocks it if the payee, amount or sender doesn't match. |
| **Read-only by default** | Each agent sees only an allowlist of MCP tools (`toolset.filtered`). Facilities and Customer Service have no write tools at all; only the Boss can change ticket status, and a ticket can't be marked `resolved` while an approval is pending. |
| **Audit logging** | Every step is appended to `output/audit_trail.json` with tool args and results, delegations and token usage, including failed steps. The trail is append-only. |
| **No double work or double pay** | A ticket can't run twice at once (409). Duplicate pending requests are refused. On the Problem 9 re-run of ticket 103, every agent found the existing requests and prepared nothing new. An approval can't be repeated, and a payment is refused if checking can't cover it, as with the $264 PO against $160. |
| **Safe dashboard defaults** | Approve stays disabled until a human types their name, which is stored on the payment. Reset needs a second click. The board shows "If all approved" in amber before an approval would overdraw checking. |

**Token and loop limits** (`backend/config.py`):

| Limit | Value | Enforced by |
|---|---|---|
| Max steps (model requests) per agent run | 8 | the audited run loop raises `AgentStepLimitExceeded` |
| Max steps per ticket (all agents) | 30 | PydanticAI `UsageLimits.request_limit`, with usage shared across delegations |
| Max tool calls per ticket | 40 | `UsageLimits.tool_calls_limit` |
| Max tokens per ticket (input + output) | 250,000 | `UsageLimits.total_tokens_limit` |
| Max delegation depth | 2 (Boss → specialist → specialist) | `delegate` returns an error past depth 2 |
| Max delegations per ticket | 6 | `delegate` returns an error after 6 |
| No self-delegation | none | `delegate` refuses |
| Model request timeout | 60s, 2 retries | OpenAI client |

When a delegation hits a limit, the caller gets `{"error": ...}` back and must finish with what it has. When the ticket-wide limit is hit, the run stops and an `error` record is audited. In test runs against a scratch DB copy, a full ticket used 12–18 model requests and about 34k–60k tokens, so these caps leave headroom without allowing runaway loops.

## API Routes

FastAPI app in `backend/main.py`. Start it from inside `backend/` with `uvicorn main:app --reload --port 8000`. CORS allows `http://localhost:5173`. The API reads and writes the DB through `backend/shop_db.py`, which agents never touch, so the approve route is the only code in the system that moves cash.

- `GET /tickets`: lists every ticket with `id`, `title` (the subject), `status`, the detailed DB status, and the latest run's state. `status` is `open` while the agent team still has work to do (`open`/`in_progress`) and `resolved` once the team has finished. `detailed_status` says whether it's fully resolved or waiting on a human (`waiting_on_approval`, `waiting_on_customer`, `waiting_on_vendor`).
- `POST /tickets/{ticket_id}/run`: starts the agent team on the ticket in the background, Boss first. Returns 202 with a `session_id` right away; 404 for an unknown ticket, 409 if it's already running.
- `GET /events?ticket_id=&since=`: returns agent events from `output/audit_trail.json`, oldest first. Each has an `id`, timestamp, agent, message, tools used, delegation targets and tokens. `since` is the last event id seen (or an ISO timestamp), so polling never repeats an event.
- `GET /approvals`: lists the pending payments, purchase orders and price overrides the agents prepared (`approval_requests` with status `pending`).
- `POST /approvals/{id}/approve`: **the only place cash changes.** Body: `{"approved_by": "<human name>"}`. Everything happens in one transaction. It re-checks the amount against the lease or invoice, refuses if checking can't cover it, writes a `payments` row (`paid_at` = `desk.date_today`), deducts from `cash_accounts` checking, marks the invoice `paid` (or moves the lease's `next_due` forward a month), and marks the request `approved`. A price override is marked approved with no cash change. If that was the ticket's last pending request and the ticket was `waiting_on_approval`, the ticket becomes `resolved`. Returns 404 for an unknown id and 409 if the request isn't pending or the funds are short.
- `GET /cash`: shows the current checking balance and `as_of` date from `cash_accounts`, plus the total pending outflow and what would be left if everything pending were approved.
- `POST /reset`: copies `data/campus_customs.db` over `data/campus_customs_new.db` for a clean run. Refused with 409 while a ticket is running. The append-only audit trail is kept.

## Dashboard

React + Vite + TypeScript app in `frontend/`. Start it with `npm run dev` (http://localhost:5173), with the API running on :8000. Full design rationale is in `output/design.md`.

| Area | What it shows | API it uses |
|---|---|---|
| Top bar | Business date, **checking balance** (counts down with a red flash when cash leaves), pending total, "If all approved" (amber if it would overdraw), approver name, Reset (two clicks) | `GET /cash`, `POST /reset` |
| Desk queue (left) | The three tickets with Open / Running / Resolved and what each is waiting on, plus an "x/3 resolved" bar | `GET /tickets` |
| Stage (center) | The ticket brief and **Run** button. A numbered **hand-off relay** (e.g. Ticket → Boss → Inventory → Accounting). **Five agent cards**, each in its own color and icon, showing live state, messages, tools called and hand-offs; agents not used show as "Not needed". A **live activity** feed. A **who-did-what** summary with the Boss's verdict and the customer reply draft | `POST /tickets/{id}/run`, `GET /events?ticket_id=&since=` (every 1.2s while running) |
| Sign-off (right) | Pending payments, POs and discounts, each with the preparing agent, its reason, and an **Approve** button | `GET /approvals`, `POST /approvals/{id}/approve` |

- **When a run finishes:** the ticket gets a green RESOLVED stamp and confetti in the agent colors.
- **Deep links:** `?ticket=102` opens the board on a ticket. This is how the screenshots in `output/screenshots/` were captured.
- **Resolved board:** `output/resolved_board.html` is a self-contained page with those screenshots embedded.

## Run results

The full run happened on 2026-10-14 (UTC), on business date 2026-08-31. It started right after a reset, and every number below comes from `output/audit_trail.json` and the working DB. Details are in `output/desk_tickets.html` (Expected vs. Actual, Cash tab) and `output/resolved_tickets.json`.

| Ticket | Delegation chain | Final status | Human approvals | Cash |
|---|---|---|---|---|
| 101 Bulldog tee | Boss → Inventory → Accounting (nested), Boss → Customer Service | `waiting_on_customer` | #1 invoice 501, $840: approved | −$840.00 |
| 102 Rent due | Boss → Facilities, Boss → Accounting (×2, re-checked after a mid-run approval) | `resolved` | #2 rent, $2,400: approved | −$2,400.00 |
| 103 Bulk hoodie discount | Boss → Accounting + Inventory (parallel), Boss → Customer Service | `waiting_on_approval` | #3 10% discount: approved (no cash). #4 PO, $264: pending (only $160 left) | $0.00 |

- **Checking:** $3,400.00 − $840.00 − $2,400.00 = **$160.00**, which equals `cash_accounts.checking` exactly.
- **Agent usage:** 4 agent runs (103 was run twice), 64 audited steps, about 217k tokens in total. No run hit a step, delegation or token limit, and no step errored.
- **Planned vs. actual:**
  - **Routing:** every ticket went to the planned first agent and used only the agents it needed.
  - **103 discount:** Accounting picked 10%, not the predicted 12.5%.
  - **Final statuses:** these shifted because the human approved some requests while the agents were still finishing.
