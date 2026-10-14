import type { CSSProperties } from "react";
import { ArrowRight } from "lucide-react";
import { AGENT_BY_NAME } from "../agents";
import { clock } from "../format";
import type { AgentEvent } from "../types";
import { AgentAvatar, agentStyle } from "./AgentAvatar";

export function Timeline({ events, running }: { events: AgentEvent[]; running: boolean }) {
  const newestFirst = [...events].reverse();
  return (
    <section className="panel timeline" aria-label="Live activity">
      <header className="panel__head">
        <h2>Live activity</h2>
        {running && <span className="live-badge">● Live</span>}
        <span className="muted">{events.length} events</span>
      </header>
      {!events.length ? (
        <p className="empty">{running ? "Boss is reading the ticket…" : "No activity yet. Pick a ticket and press Run."}</p>
      ) : (
        <ol className="feed">
          {newestFirst.map((e) => (
            <li
              key={e.id}
              className={`feed__item feed__item--${e.kind}`}
              style={{ ...agentStyle(e.agent), "--depth": e.depth } as CSSProperties}
            >
              <AgentAvatar agent={e.agent} size="sm" />
              <div className="feed__body">
                <div className="feed__meta">
                  <strong>{AGENT_BY_NAME[e.agent].label}</strong>
                  {e.kind === "final" && <span className="tag tag--report">Report</span>}
                  {e.kind === "error" && <span className="tag tag--error">Error</span>}
                  <time dateTime={e.timestamp}>{clock(e.timestamp)}</time>
                </div>
                {e.delegated_to.length > 0 && (
                  <div className="feed__handoff">
                    {e.delegated_to.map((to) => (
                      <span key={to} className="chip chip--handoff" style={agentStyle(to)}>
                        <ArrowRight size={12} aria-hidden /> {AGENT_BY_NAME[to].label}
                      </span>
                    ))}
                  </div>
                )}
                <p className="feed__msg">{e.message}</p>
                {e.tool_calls.some((c) => c.tool !== "delegate") && (
                  <ul className="chips">
                    {e.tool_calls
                      .filter((c) => c.tool !== "delegate")
                      .map((c, i) => (
                        <li key={i} className="chip chip--tool" title={JSON.stringify(c.args)}>
                          {c.tool}
                        </li>
                      ))}
                  </ul>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
