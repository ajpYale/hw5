"""Customer Service: drafts what the customer is told. Read-only."""

from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models import Model

from backend.agents.base import make_agent
from backend.models import SpecialistReport

NAME = "customer_service"
MCP_TOOLS = frozenset({"get_ticket", "check_stock", "list_approval_requests"})


def build(model: Model, mcp: MCPToolset):
    return make_agent(NAME, model, mcp, MCP_TOOLS, SpecialistReport)
