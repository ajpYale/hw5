"""Facilities: the shop lease and rent notices. Read-only; money goes to Accounting."""

from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models import Model

from backend.agents.base import make_agent
from backend.models import SpecialistReport

NAME = "facilities"
MCP_TOOLS = frozenset(
    {"get_ticket", "verify_rent_due", "list_payments", "list_approval_requests"}
)


def build(model: Model, mcp: MCPToolset):
    return make_agent(NAME, model, mcp, MCP_TOOLS, SpecialistReport)
