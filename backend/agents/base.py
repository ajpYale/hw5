"""Shared plumbing for every role: agent factory, delegation tool, audited run loop."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel
from pydantic_ai import (
    Agent,
    AgentRunError,
    ModelRequest,
    RetryPromptPart,
    RunContext,
    RunUsage,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models import Model

from backend.audit import append_record
from backend.config import (
    MAX_DELEGATION_DEPTH,
    MAX_DELEGATIONS_PER_TICKET,
    MAX_STEPS_PER_AGENT_RUN,
    PROMPTS_DIR,
    TICKET_LIMITS,
)
from backend.mcp_toolset import tools_for
from backend.models import AgentName, AuditRecord, TokenUsage, ToolCallRecord

DELEGATE_TOOL = "delegate"


class AgentStepLimitExceeded(AgentRunError):
    """One agent made more model requests in a single run than allowed."""


@dataclass
class TicketBudget:
    """Counters shared by every agent working the same ticket."""

    delegations_used: int = 0
    usage: RunUsage = field(default_factory=RunUsage)


@dataclass
class TeamDeps:
    """Per-run context. A delegation makes a child copy one level deeper."""

    team: dict[str, Agent[TeamDeps, Any]]
    session_id: str
    ticket_id: int
    agent: AgentName
    depth: int
    delegated_by: AgentName | None
    budget: TicketBudget

    def child(self, target: AgentName) -> TeamDeps:
        return TeamDeps(
            team=self.team,
            session_id=self.session_id,
            ticket_id=self.ticket_id,
            agent=target,
            depth=self.depth + 1,
            delegated_by=self.agent,
            budget=self.budget,
        )


async def delegate(ctx: RunContext[TeamDeps], agent: AgentName, request: str) -> dict[str, Any]:
    """Hand a sub-task to another agent on the team and get its report back.

    Team: boss (coordinates, owns ticket status), inventory (stock, vendors,
    restock purchase orders), accounting (invoices, payments, cash, discounts
    and margins), facilities (lease and rent notices), customer_service
    (customer-facing replies). Delegation depth and total delegations per
    ticket are capped; if a limit is hit you get {"error": ...} back and must
    finish with what you already know.

    Args:
        agent: Who to hand off to. Must not be yourself.
        request: A specific, self-contained task. Include the ticket id and
            the facts you already checked so they don't redo your work.
    """
    deps = ctx.deps
    if agent == deps.agent:
        return {"error": "You can't delegate to yourself."}
    if deps.depth + 1 > MAX_DELEGATION_DEPTH:
        return {
            "error": f"Max delegation depth ({MAX_DELEGATION_DEPTH}) reached. "
            "Finish with the facts you have and say what is still unchecked."
        }
    if deps.budget.delegations_used >= MAX_DELEGATIONS_PER_TICKET:
        return {
            "error": f"This ticket used all {MAX_DELEGATIONS_PER_TICKET} delegations. "
            "Finish with the facts you have."
        }
    deps.budget.delegations_used += 1
    prompt = f"Ticket {deps.ticket_id}. Request from {deps.agent}: {request}"
    try:
        output = await run_agent(agent, prompt, deps.child(agent))
    except AgentRunError as exc:
        return {"error": f"{agent} could not finish: {exc}"}
    return output.model_dump(mode="json")


def load_prompt(name: AgentName) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def make_agent(
    name: AgentName,
    model: Model,
    mcp: MCPToolset,
    mcp_tools: frozenset[str],
    output_type: type[BaseModel],
) -> Agent[TeamDeps, Any]:
    """Build one role: its prompt file, its MCP tool allowlist, and delegate()."""
    return Agent(
        model,
        name=name,
        instructions=load_prompt(name),
        output_type=output_type,
        deps_type=TeamDeps,
        toolsets=[tools_for(mcp, mcp_tools)],
        tools=[delegate],
        retries=2,
    )


# --- Audited run loop -----------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _usage(u: Any) -> TokenUsage:
    return TokenUsage(
        input_tokens=u.input_tokens or 0,
        output_tokens=u.output_tokens or 0,
        total_tokens=u.total_tokens or 0,
        requests=getattr(u, "requests", 0) or 0,
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    try:
        json.dumps(value)
        return value
    except TypeError:
        return json.loads(json.dumps(value, default=str))


def _describe_request(request: ModelRequest) -> Any:
    """What the model was given for this step: the prompt, or tool results."""
    items: list[Any] = []
    for part in request.parts:
        if isinstance(part, UserPromptPart):
            items.append(part.content)
        elif isinstance(part, ToolReturnPart):
            items.append({"tool_result_for": part.tool_name})
        elif isinstance(part, RetryPromptPart):
            items.append({"retry_for": part.tool_name, "error": _jsonable(part.content)})
    return items[0] if len(items) == 1 and isinstance(items[0], str) else items


def _results_by_call_id(request: ModelRequest) -> dict[str, Any]:
    results = {}
    for part in request.parts:
        if isinstance(part, ToolReturnPart):
            results[part.tool_call_id] = _jsonable(part.content)
        elif isinstance(part, RetryPromptPart) and part.tool_call_id:
            results[part.tool_call_id] = {"retry": _jsonable(part.content)}
    return results


class _StepLog:
    """Buffers one step until its tool results are known, then appends it."""

    def __init__(self, deps: TeamDeps):
        self.deps = deps
        self.step = 0
        self.pending: dict[str, Any] | None = None

    def open(self, step_input: Any, response: Any) -> None:
        self.step += 1
        self.pending = {
            "input": step_input,
            "calls": [(c.tool_call_id, c.tool_name, c.args_as_dict()) for c in response.tool_calls],
            "text": response.text,
            "usage": _usage(response.usage),
        }

    def close(
        self,
        results: dict[str, Any],
        event: str = "step",
        output: Any = None,
    ) -> None:
        if self.pending is None:
            return
        p, self.pending = self.pending, None
        if event == "final":  # the output tool's return never reaches a next request
            for call_id, name, _ in p["calls"]:
                results.setdefault(call_id, "accepted as final output (see `output`)")
        calls = [
            ToolCallRecord(
                tool=name,
                args=args,
                result=results.get(call_id),
                delegation_target=args.get("agent") if name == DELEGATE_TOOL else None,
            )
            for call_id, name, args in p["calls"]
        ]
        self.write(
            event=event,
            step_input=p["input"],
            calls=calls,
            output=output if output is not None else p["text"],
            step_usage=p["usage"],
        )

    def write(
        self,
        *,
        event: str,
        step_input: Any,
        calls: list[ToolCallRecord],
        output: Any,
        step_usage: TokenUsage,
    ) -> None:
        append_record(
            AuditRecord(
                timestamp=_now(),
                session_id=self.deps.session_id,
                ticket_id=self.deps.ticket_id,
                agent=self.deps.agent,
                depth=self.deps.depth,
                delegated_by=self.deps.delegated_by,
                step=self.step,
                event=event,
                input=step_input,
                tool_calls=calls,
                delegation_targets=[c.delegation_target for c in calls if c.delegation_target],
                output=_jsonable(output),
                step_usage=step_usage,
                ticket_usage_so_far=_usage(self.deps.budget.usage),
            )
        )


async def run_agent(name: AgentName, prompt: str, deps: TeamDeps) -> Any:
    """Run one agent to completion, appending an audit record for every step.

    All agents on a ticket share one RunUsage, so TICKET_LIMITS (steps, tool
    calls, tokens) apply to the whole ticket. MAX_STEPS_PER_AGENT_RUN caps a
    single agent's loop on top of that.
    """
    agent = deps.team[name]
    log = _StepLog(deps)
    step_input: Any = prompt
    requests_made = 0
    try:
        async with agent.iter(
            prompt, deps=deps, usage=deps.budget.usage, usage_limits=TICKET_LIMITS
        ) as run:
            async for node in run:
                if Agent.is_model_request_node(node):
                    log.close(_results_by_call_id(node.request))
                    step_input = _describe_request(node.request)
                    requests_made += 1
                    if requests_made > MAX_STEPS_PER_AGENT_RUN:
                        raise AgentStepLimitExceeded(
                            f"{name} hit the {MAX_STEPS_PER_AGENT_RUN}-step limit for one run."
                        )
                elif Agent.is_call_tools_node(node):
                    log.close({})  # defensive; normally closed by the next request
                    log.open(step_input, node.model_response)
            output = run.result.output
        log.close({}, event="final", output=output)
        return output
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        if log.pending is not None:
            log.close({}, event="error", output=message)
        else:
            log.step += 1  # the step whose model request failed
            log.write(
                event="error",
                step_input=step_input,
                calls=[],
                output=message,
                step_usage=TokenUsage(),
            )
        raise
