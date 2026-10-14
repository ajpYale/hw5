"""The one data source for every agent: the campus-customs MCP server over stdio."""

import os

from fastmcp.client.transports import StdioTransport
from pydantic_ai import AbstractToolset
from pydantic_ai.mcp import MCPToolset

from backend.config import MCP_SERVER_PATH, PROJECT_ROOT, PYTHON


def build_mcp_toolset() -> MCPToolset:
    """Launch mcp_server/server.py with this venv's Python.

    CAMPUS_CUSTOMS_DB is forwarded so tests can point the server at a scratch DB.
    """
    env = {k: os.environ[k] for k in ("CAMPUS_CUSTOMS_DB",) if k in os.environ}
    transport = StdioTransport(
        command=PYTHON,
        args=[str(MCP_SERVER_PATH)],
        env=env or None,
        cwd=str(PROJECT_ROOT),
    )
    return MCPToolset(transport, id="campus-customs")


def tools_for(toolset: MCPToolset, allowed: frozenset[str]) -> AbstractToolset:
    """Expose only the MCP tools a role is allowed to call."""
    return toolset.filtered(lambda ctx, tool_def: tool_def.name in allowed)
