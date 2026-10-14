# AI Prompts Log — HW 5

Running log of the prompts given to the AI assistant for each problem in this homework.

---

## Problem 1: Vibe coder prompts

### Prompt

> Create a file called AI_prompts.md at the project root. It's a running log of the prompts I give you for this homework. Add one section per problem (Problems 1–11), each with: the problem number and title, a "Prompt" subsection, and a "Follow-up (if needed)" subsection with a one-line note on what the first attempt was missing. Fill in Problem 1 with this prompt. After each future problem, remind me to paste my prompt into the matching section.

### Follow-up (if needed)

Looks good.

---

## Problem 2: Study the Campus Customs database

### Prompt

> Open data/campus_customs.db and inspect every table (desk, tickets, inventory, pricing, vendors, leases, cash_accounts, payments, invoices, plus anything else that's there). First, copy it to data/campus_customs_new.db — that's our working copy for the rest of the homework; never modify the original. Then show me the three open tickets and trace how each one links to other tables (foreign keys, matching ids, vendor/invoice/lease references, etc).Create output/harness.md with a "Database" section. For each table: list every field with its type, and write one short line on why that table matters to the agents. Only use what's actually in the DB — do not invent fields. Add a short "Open tickets" subsection summarizing tickets 101, 102, 103 and which tables each one touches.

### Follow-up (if needed)

None — first attempt was complete.

---

## Problem 3: Build the MCP server

### Prompt

> Build an MCP server in mcp_server/server.py using FastMCP. It reads and writes data/campus_customs_new.db (use a path relative to the project root so it works from any folder). Don't run or connect it yet. Based on what we learned about tickets 101, 102, and 103, write three tools the agents will definitely need to work those tickets. Give them clear names, typed parameters, and docstrings. Every value returned must come from the database — never fabricate data; return a clear error if a record isn't found. In output/harness.md add an "MCP Tools" section. For each tool list: the tool name, which table(s) it reads, which ticket (101, 102, or 103) it unlocks, and one specific sentence on why it's the right tool for that ticket (not generic like "reads inventory"). Also create mcp_server/README.md explaining what the server does, which DB file it uses, and the three tools.

### Follow-up (if needed)

None — first attempt was complete.

---

## Problem 4: Connect the MCP server and smoke test it

### Prompt

> register the MCP server from mcp_server/server.py with this project so you (the vibe coder) can call its tools. Save the config as .mcp.json at the project root using the corct format for this tool, and tell me if I need to restart or approve anything. Once connected, call each of the three tols for real with a realistic request tied to a ticket. Then create output/mcp_smoke.json with an array of entries, one per tool, each containing: "prompt" (what I asked), "tool" (tool name), and "output" (the actual tool response). Afterward, query data/campus_customs_new.db directly and confirm each output matches the database. Don't fake or paraphrase outputs.

### Follow-up (if needed)

The first session could only register the server; Claude Code had to restart and approve it before the tools showed up, so a follow-up ran the three calls, wrote mcp_smoke.json, and checked it against the DB.

---

## Problem 5: Build the agent team and grow the MCP tools

### Prompt

> Build a five-agent team in backend/ using PydanticAI: Boss, Inventory, Accounting, Facilities, and Customer Service.
> Setup:
> - Every agent uses the model gpt-6-luna via Portkey, using PORTKEY_API_KEY from .env. No other models.
> - Put shared Pydantic data types in backend/models.py.
> - One agent file per role under backend/agents/ (or similar).
> - One system prompt file per agent in backend/prompts/: boss.md, inventory.md, accounting.md, facilities.md, customer_service.md.
> Connectivity: the Boss receives a ticket and decides who to call first. Any agent can delegate to any other agent (expose delegation as tools), with a max delegation depth and max steps per run so it can't loop forever.
> Data: agents get ALL shop facts through the MCP server (connect PydanticAI to mcp_server/server.py as an MCP toolset). Do not create a second set of direct-DB tools. Add whatever new MCP tools are needed to fully work tickets 101–103 (e.g., checking invoices/payments, preparing a payment, updating ticket status) and update mcp_server/README.md. Prompts: write detailed prompts covering each agent's role, scope, what it must NOT do, which tools it should use, and when to hand off. Include shop rules like: use desk.date_today to judge whether something is overdue; never ship an order with an unpaid invoice; agents may only PREPARE payments/purchases — a human must approve before cash moves; never invent data.
> Audit: every agent-loop step appends a record to output/audit_trail.json (timestamp, ticket id, agent, input, tool calls + args + results, delegation target, output, token usage). Append — never overwrite. Update output/harness.md: list each agent and its job; list every MCP tool with the table(s) it uses; add a "Safety" section with guardrails a real business needs (human approval for money, spend caps, no customer PII leakage, read-only defaults, audit logging) plus token limits (max steps, max delegations, max tokens per run).

### Follow-up (if needed)

None — first attempt was complete.

---

## Problem 6: Plan the three tickets

### Prompt

> Create output/desk_tickets.html — a single self-contained HTML file (inline CSS/JS, opens by double-clicking) with tabs: Ticket 101, Ticket 102, Ticket 103, Cash, and Reflection.On each ticket tab, add an "Expected" section and an empty "Actual" section (placeholder text: "To be filled after the run"). Fill Expected for each ticket using the actual ticket data in the DB:
> - Who the Boss should call first and why
> - The specific chain of delegations I expect (only the agents actually needed — not "Boss calls everyone")
> - Which MCP tools I expect to be used, by which agent
> Cash and Reflection tabs: just a "Coming later" note for now. Before writing, show me your draft plan for each ticket so I can adjust it.

### Follow-up (if needed)

The draft plan didn't commit to a discount rate for 103 (it said "10–15%"), so I replied "go, use 12.5% for 103".

---

## Problem 7: Backend routes

### Prompt

> In backend/main.py create a FastAPI app with these routes:
> - GET  /tickets — the three tickets with id, title, and open/resolved status
> - POST /tickets/{ticket_id}/run — runs the agent team on that ticket (Boss starts)
> - GET  /events?ticket_id=&since= — recent agent events: agent name, message, tools used, timestamp (pulled from the audit trail or an in-memory event log) so the frontend can poll
> - GET  /approvals — pending payments/purchases the agents prepared
> - POST /approvals/{id}/approve — the ONLY place cash actually changes; marks the payment approved, updates payments/invoices, and deducts from cash_accounts checking
> - GET  /cash — current checking balance from cash_accounts
> - POST /reset — copies data/campus_customs.db over data/campus_customs_new.db for a clean run Agents must never move money themselves. Add CORS for http://localhost:5173. Make sure it starts with `uvicorn main:app --reload --port 8000` from inside backend/. Add an "API Routes" section to output/harness.md with one line per route (method, URL, what it does). Then start the server and hit each GET route to confirm it works.

### Follow-up (if needed)

None — first attempt was complete.

---

## Problem 8: Agent dashboard

### Prompt

> Build a frontend in frontend/ using React + Vite + TypeScript that talks to http://localhost:8000.
> The board must:
> - List all three tickets with open/resolved status
> - Let me pick a ticket and click "Run" to start the agent team
> - Show each of the five agents live while a ticket runs (poll /events) — what they're saying, who they delegated to, which tools they called
> - Mark the ticket resolved when the run finishes
> - Show a per-agent summary of what each agent did on that ticket
> - Show pending payments/purchases with an "Approve" button (calls the approve route)
> - Show the checking balance prominently, updating after an approval
> - Have a Reset button
> Design: make it look like a real operations desk, not the default Vite template. Give each agent a distinct color/avatar/icon, show handoffs visually (e.g., a flow or timeline between agent cards), make resolved tickets feel satisfying, and make the cash balance animate when it drops. Choose a cohesive color palette and typography. Then write output/design.md explaining the layout, how agents are visually distinguished, how resolved tickets and cash are shown, and the creative choices and why they make the desk pleasant to use. Start it with `npm run dev` and tell me what to check.

### Follow-up (if needed)

None — first attempt was complete.

---

## Problem 9: Resolve the tickets

### Prompt

> Let's do the full run. First reset data/campus_customs_new.db from the original and record the starting checking balance from cash_accounts. I'll run tickets 101, 102, and 103 on the board and approve payments when prompted — tell me when to do each step.
> After all three are resolved:
> 1. In output/desk_tickets.html, fill each ticket's "Actual" section from output/audit_trail.json: which agents worked, the actual delegation chain, and which tools were used. Keep Expected next to it.
> 2. Fill the Cash tab: starting balance, then for each ticket the cash change, which payment/purchase caused it, and the dollar amount, then the ending balance. Query the DB and confirm the ending balance matches cash_accounts exactly — show me the math.
> 3. Create output/resolved_tickets.json: for each ticket — id, final status, short outcome, each agent's contribution, and any human approvals.
> 4. Create output/resolved_board.html, a self-contained page (images embedded as base64) showing a screenshot of the board for each resolved ticket. I'll save screenshots to output/screenshots/ticket_101.png, etc.
> 5. Finish output/harness.md so it covers tables, MCP tools, the five agents, API routes, the dashboard, and safety rules.

### Follow-up (if needed)

The first reply only gave me run instructions, so I asked "how do i run, can you run". Claude then drove the board, approved as me per the plan (invoice, rent, discount; PO left pending), and captured the screenshots itself.

---

## Problem 10: Reflection

### Prompt

> fill the Reflection tab in output/desk_tickets.html. Use the Expected/Actual sections, the Cash tab, resolved_tickets.json, and audit_trail.json as evidence, and cite specific ticket ids, agents, tools, and dollar amounts. Sections:
> 1. How well did the agents perform on each ticket and why?
> 2. For each ticket, how did Actual compare to Expected? Where did they differ?
> 3. What would have been simpler as a single agent with tools, and why?
> 4. Three new problems Campus Customs could face that this team CAN solve with the existing tools (explain which agents/tools).
> 5. Three new problems this team CANNOT solve, and what new tools and agents would be needed.
> Start by summarizing what the evidence shows; I'll add my own opinions before you write the final version. No generic AI essay — every point must be tied to this app.

### Follow-up (if needed)

Planned two-step: after the evidence summary I replied "keep your candidates, 10% was fine, write the final version".
