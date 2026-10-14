# Campus Customs Ops Desk (MGT 409, Homework 5)

A five-agent team (Boss, Inventory, Accounting, Facilities, Customer Service) works the Campus Customs desk tickets. The agents use PydanticAI with `gpt-6-luna` via Portkey. Every shop fact comes through the **campus-customs MCP server**. A **FastAPI** backend runs the team, and a **React** board shows the agents live.

Agents can only *prepare* payments, restock orders and discounts. Cash moves only when a human clicks **Approve** on the board (`POST /approvals/{id}/approve`).

```
frontend/ (React board, :5173)  →  backend/main.py (FastAPI, :8000)  →  agent team  →  mcp_server/server.py  →  data/campus_customs_new.db
```

Full documentation is in `output/harness.md`: tables, MCP tools, agents, API routes, dashboard and safety rules.

## Prerequisites

- Python 3.11+ (built and tested on 3.14)
- Node.js 20.19+ or 22+ (for Vite)
- A Portkey API key with access to `gpt-6-luna`

## One-time setup

```bash
# 1. Python environment (from the project root)
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # macOS/Linux: .venv/bin/pip install -r requirements.txt

# 2. API key
cp .env.example .env                                # then edit .env and set PORTKEY_API_KEY

# 3. Frontend packages
cd frontend
npm install
cd ..
```

Activate the venv in each terminal you use below (`.venv\Scripts\activate` on Windows, `source .venv/bin/activate` on macOS/Linux) so `python` and `uvicorn` come from it.

## 1. Copy the original database to the working copy

`data/campus_customs.db` is the original and is never modified. Everything runs against the working copy, `data/campus_customs_new.db`:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

Once the backend is running, the board's **Reset** button (or `POST /reset`) does the same copy.

## 2. Start the MCP server

You don't need to start it by hand. It runs over stdio and is launched by its clients:

- **The agent team** starts it automatically for each ticket run (`backend/mcp_toolset.py`), using the venv's Python.
- **Claude Code** connects using `.mcp.json` at the project root. The paths there are relative and Windows-style. On macOS/Linux, change `command` to `.venv/bin/python`.

To start it manually, for example to debug it:

```bash
python mcp_server/server.py
```

## 3. Start the FastAPI backend

Run this from inside `backend/`:

```bash
cd backend
uvicorn main:app --reload --port 8000
```

The API is then at http://localhost:8000 (interactive docs at http://localhost:8000/docs). CORS allows the board at `http://localhost:5173`.

## 4. Start the React board

In a second terminal:

```bash
cd frontend
npm run dev
```

Open **http://localhost:5173**. Use `localhost`, not `127.0.0.1`. Type your name in the approver box at the top right; Approve stays disabled until you do.

## 5. Reset before a full three-ticket run

With the backend and board running:

1. Click **Reset** on the board and confirm with a second click, or run `curl -X POST http://localhost:8000/reset`. Checking returns to **$3,400.00** and all three tickets go back to Open.
2. Select **#101** → **Run** → wait for **Resolved** → approve its payment in "Needs your sign-off".
3. Do the same for **#102**, then **#103**.

Reset is refused while a ticket is running. `output/audit_trail.json` is append-only, so a reset never erases it.

A ticket can also be run without the board, from the project root:

```bash
python -m backend.run_ticket 101
```

## Project layout

| Path | What it is |
|---|---|
| `mcp_server/` | FastMCP server (13 tools) and its README |
| `backend/` | `main.py` (FastAPI), `models.py` (shared Pydantic types), `agents/` (one file per role), `prompts/` (one system prompt per agent), `shop_db.py` (API-only DB access, including the one cash-moving function) |
| `frontend/` | React + Vite + TypeScript ops desk |
| `data/` | `campus_customs.db` (original) and `campus_customs_new.db` (working copy, left in its state after the Problem 9 run) |
| `output/` | `harness.md`, `mcp_smoke.json`, `desk_tickets.html`, `design.md`, `resolved_tickets.json`, `resolved_board.html` (+ `screenshots/`), `audit_trail.json` |
| `AI_prompts.md` | The prompts used for each problem |
