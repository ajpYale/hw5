import type { CSSProperties } from "react";
import { AGENT_BY_NAME } from "../agents";
import type { AgentName } from "../types";

interface Props {
  agent: AgentName;
  size?: "xs" | "sm" | "md" | "lg";
  pulse?: boolean;
}

export function agentStyle(agent: AgentName): CSSProperties {
  return { "--agent": AGENT_BY_NAME[agent].color } as CSSProperties;
}

export function AgentAvatar({ agent, size = "md", pulse = false }: Props) {
  const meta = AGENT_BY_NAME[agent];
  const Icon = meta.icon;
  return (
    <span
      className={`avatar avatar--${size}${pulse ? " avatar--pulse" : ""}`}
      style={agentStyle(agent)}
      title={meta.label}
      aria-label={meta.label}
    >
      <Icon aria-hidden strokeWidth={2.2} />
    </span>
  );
}

export function AgentTag({ agent }: { agent: AgentName }) {
  return (
    <span className="agent-tag" style={agentStyle(agent)}>
      <AgentAvatar agent={agent} size="xs" />
      {AGENT_BY_NAME[agent].label}
    </span>
  );
}
