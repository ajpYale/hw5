"""Accounting: invoices, payments, cash, discounts and margins."""

from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models import Model

from backend.agents.base import make_agent
from backend.models import SpecialistReport

NAME = "accounting"
MCP_TOOLS = frozenset(
    {
        "get_ticket",
        "check_invoice",
        "list_payments",
        "list_approval_requests",
        "verify_rent_due",
        "quote_bulk_discount",
        "prepare_payment",
        "prepare_price_override",
    }
)


def build(model: Model, mcp: MCPToolset):
    return make_agent(NAME, model, mcp, MCP_TOOLS, SpecialistReport)
