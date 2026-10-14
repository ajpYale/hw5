"""Shared Pydantic data types for the Campus Customs agent team."""

from typing import Any, Literal

from pydantic import BaseModel, Field

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
AGENT_NAMES: tuple[AgentName, ...] = (
    "boss",
    "inventory",
    "accounting",
    "facilities",
    "customer_service",
)

TicketStatus = Literal[
    "open",
    "in_progress",
    "waiting_on_approval",
    "waiting_on_customer",
    "waiting_on_vendor",
    "resolved",
]


# --- Agent outputs -----------------------------------------------------------


class Fact(BaseModel):
    """One fact an agent relied on, tied to the tool that returned it."""

    source_tool: str = Field(description="MCP tool (or 'delegate') that returned this fact.")
    detail: str = Field(description="The fact, with the exact numbers/dates from the tool.")


class SpecialistReport(BaseModel):
    """What a specialist agent hands back to whoever delegated to it."""

    agent: AgentName
    ticket_id: int
    summary: str = Field(description="Two or three sentences answering the request.")
    facts: list[Fact] = Field(description="Facts checked, each from a tool result.")
    approval_requests_created: list[int] = Field(
        default_factory=list,
        description="ids of approval_requests rows this agent prepared (empty if none).",
    )
    recommendation: str = Field(description="What should happen next, and who should do it.")
    needs_human_approval: bool = Field(
        description="True if anything here moves money, orders stock or changes a price."
    )
    blocked: str | None = Field(
        default=None, description="Why the request can't be completed, if it can't."
    )


class ApprovalItem(BaseModel):
    """A pending approval request the human owner must decide on."""

    request_id: int
    kind: Literal["rent", "invoice", "purchase_order", "price_override"]
    amount: float
    description: str


class TicketResolution(BaseModel):
    """The Boss's final answer for one ticket."""

    ticket_id: int
    final_status: TicketStatus
    summary: str = Field(description="What was found and decided, in plain language.")
    agents_consulted: list[AgentName]
    decisions: list[str] = Field(description="Each decision made, with the fact behind it.")
    approvals_needed: list[ApprovalItem] = Field(
        description="Pending approval requests for this ticket that a human must decide on."
    )
    customer_message: str | None = Field(
        default=None, description="Draft message to the requester, if one is needed."
    )
    risks: list[str] = Field(default_factory=list, description="Open risks or caveats.")


# --- Audit trail -------------------------------------------------------------


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    requests: int = 0


class ToolCallRecord(BaseModel):
    tool: str
    args: dict[str, Any]
    result: Any = None
    delegation_target: AgentName | None = None


class AuditRecord(BaseModel):
    """One agent-loop step (one model response plus the tools it called)."""

    timestamp: str
    session_id: str = Field(description="One id per ticket run, shared by every agent in it.")
    ticket_id: int
    agent: AgentName
    depth: int = Field(description="0 for the Boss, +1 per delegation hop.")
    delegated_by: AgentName | None
    step: int
    event: Literal["step", "final", "error"]
    input: Any
    tool_calls: list[ToolCallRecord]
    delegation_targets: list[AgentName]
    output: Any
    step_usage: TokenUsage
    ticket_usage_so_far: TokenUsage
