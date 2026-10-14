import type { CSSProperties } from "react";
import { ArrowRight, CornerDownRight } from "lucide-react";
import { AGENTS, AGENT_BY_NAME } from "../agents";
import type { AgentActivity, Hop } from "../format";
import type { AgentName } from "../types";
import { AgentAvatar, agentStyle } from "./AgentAvatar";

const STATE_LABEL = {
  idle: "Standing by",
  working: "Working",
  done: "Reported",
  error: "Error",
} as const;

interface Props {
  activity: Map<AgentName, AgentActivity>;
  hops: Hop[];
  running: boolean;
  hasSession: boolean;
}

export function AgentFloor({ activity, hops, running, hasSession }: Props) {
  // The newest "working" agent is the one most likely thinking right now.
  const liveAgent = running
    ? [...activity.entries()]
        .filter(([, a]) => a.state === "working")
        .sort((x, y) => y[1].lastEventId - x[1].lastEventId)[0]?.[0]
    : undefined;

  return (
    <section aria-label="Agents">
      <HandoffStrip hops={hops} running={running} />
      <div className="floor">
        {AGENTS.map((meta) => {
          const a = activity.get(meta.name);
          const state = a?.state ?? "idle";
          const benched = hasSession && !running && !a;
          return (
            <article
              key={meta.name}
              className={[
                "agent",
                `agent--${state}`,
                liveAgent === meta.name ? "agent--live" : "",
                benched ? "agent--benched" : "",
              ].join(" ")}
              style={agentStyle(meta.name)}
            >
              <header className="agent__head">
                <AgentAvatar agent={meta.name} size="lg" pulse={liveAgent === meta.name} />
                <div>
                  <h3>{meta.label}</h3>
                  <p>{meta.role}</p>
                </div>
              </header>
              <div className="agent__state">
                <span className="dot" aria-hidden />
                {benched ? "Not needed" : STATE_LABEL[state]}
                {a && <span className="agent__steps">{a.steps} steps</span>}
              </div>
              {a?.calledBy.length ? (
                <div className="agent__from">
                  <CornerDownRight size={13} aria-hidden />
                  from{" "}
                  {a.calledBy.map((c) => (c === "ticket" ? "ticket" : AGENT_BY_NAME[c].label)).join(", ")}
                </div>
              ) : null}
              <p className="agent__msg">{a?.lastMessage ?? (benched ? "Sat this one out." : "Waiting for a hand-off.")}</p>
              {a && a.tools.size > 0 && (
                <ul className="chips" aria-label="Tools called">
                  {[...a.tools.entries()].map(([tool, n]) => (
                    <li key={tool} className="chip chip--tool">
                      {tool}
                      {n > 1 && <span className="chip__n">×{n}</span>}
                    </li>
                  ))}
                </ul>
              )}
              {a && a.delegatedTo.length > 0 && (
                <ul className="chips" aria-label="Handed off to">
                  {a.delegatedTo.map((to) => (
                    <li key={to} className="chip chip--handoff" style={agentStyle(to)}>
                      <ArrowRight size={12} aria-hidden /> {AGENT_BY_NAME[to].label}
                    </li>
                  ))}
                </ul>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}

function HandoffStrip({ hops, running }: { hops: Hop[]; running: boolean }) {
  if (!hops.length) {
    return (
      <div className="relay relay--empty">
        Hand-offs will appear here as the Boss routes the ticket.
      </div>
    );
  }
  return (
    <ol className="relay" aria-label="Hand-off flow">
      {hops.map((h, i) => (
        <li
          key={h.eventId}
          className={`relay__hop${running && i === hops.length - 1 ? " relay__hop--live" : ""}`}
        >
          <span className="relay__n">{i + 1}</span>
          {h.from === "ticket" ? (
            <span className="relay__ticket">Ticket</span>
          ) : (
            <AgentAvatar agent={h.from} size="sm" />
          )}
          <span
            className="relay__line"
            style={
              {
                "--from": h.from === "ticket" ? "#64748b" : AGENT_BY_NAME[h.from].color,
                "--to": AGENT_BY_NAME[h.to].color,
              } as CSSProperties
            }
            aria-hidden
          />
          <AgentAvatar agent={h.to} size="sm" />
          <span className="relay__label">
            {h.from === "ticket" ? "Ticket" : AGENT_BY_NAME[h.from].label} → {AGENT_BY_NAME[h.to].label}
          </span>
        </li>
      ))}
    </ol>
  );
}
