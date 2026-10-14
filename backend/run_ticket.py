"""Work desk tickets with the agent team.

Usage (from the project root):
    .venv/Scripts/python -m backend.run_ticket 101 [102 103 ...]

The Boss receives each ticket and decides who to call first. Every agent-loop
step is appended to output/audit_trail.json.
"""

import argparse
import asyncio
import os
import sys
import uuid

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from backend.agents import build_team
from backend.agents.base import TeamDeps, TicketBudget, run_agent
from backend.config import build_model
from backend.mcp_toolset import build_mcp_toolset
from backend.models import TicketResolution


async def work_ticket(ticket_id: int, session_id: str | None = None) -> TicketResolution:
    mcp = build_mcp_toolset()
    team = build_team(build_model(), mcp)
    deps = TeamDeps(
        team=team,
        session_id=session_id or uuid.uuid4().hex[:12],
        ticket_id=ticket_id,
        agent="boss",
        depth=0,
        delegated_by=None,
        budget=TicketBudget(),
    )
    async with mcp:  # one MCP server process shared by every agent on this ticket
        return await run_agent("boss", f"Work ticket {ticket_id}.", deps)


async def main(ticket_ids: list[int]) -> None:
    for ticket_id in ticket_ids:
        resolution = await work_ticket(ticket_id)
        print(resolution.model_dump_json(indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("ticket_ids", nargs="+", type=int)
    asyncio.run(main(parser.parse_args().ticket_ids))
