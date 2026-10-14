"""The five-agent Campus Customs team."""

from typing import Any

from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models import Model

from backend.agents import accounting, boss, customer_service, facilities, inventory
from backend.agents.base import TeamDeps

ROLES = (boss, inventory, accounting, facilities, customer_service)


def build_team(model: Model, mcp: MCPToolset) -> dict[str, Agent[TeamDeps, Any]]:
    return {role.NAME: role.build(model, mcp) for role in ROLES}
