"""Boss: receives each ticket, picks who works it first, and owns the final call."""

from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models import Model

from backend.agents.base import make_agent
from backend.models import TicketResolution

NAME = "boss"
MCP_TOOLS = frozenset(
    {"get_ticket", "list_open_tickets", "list_approval_requests", "update_ticket_status"}
)


def build(model: Model, mcp: MCPToolset):
    return make_agent(NAME, model, mcp, MCP_TOOLS, TicketResolution)
