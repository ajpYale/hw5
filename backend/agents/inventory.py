"""Inventory: stock levels, suppliers and lead times, restock purchase orders."""

from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models import Model

from backend.agents.base import make_agent
from backend.models import SpecialistReport

NAME = "inventory"
MCP_TOOLS = frozenset(
    {
        "get_ticket",
        "check_stock",
        "quote_bulk_discount",
        "list_vendors",
        "list_approval_requests",
        "prepare_purchase_order",
    }
)


def build(model: Model, mcp: MCPToolset):
    return make_agent(NAME, model, mcp, MCP_TOOLS, SpecialistReport)
