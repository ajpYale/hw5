import { MessageCircle, TriangleAlert } from "lucide-react";
import { AGENTS } from "../agents";
import { isResolution, statusLabel, type AgentActivity } from "../format";
import type { AgentName, SpecialistReport, TicketResolution } from "../types";
import { AgentAvatar, AgentTag, agentStyle } from "./AgentAvatar";

interface Props {
  activity: Map<AgentName, AgentActivity>;
  resolution: TicketResolution | null;
  running: boolean;
}

export function AgentSummary({ activity, resolution, running }: Props) {
  return (
    <section className="panel summary" aria-label="What each agent did">
      <header className="panel__head">
        <h2>Who did what</h2>
      </header>

      {resolution && (
        <div className="verdict">
          <div className="verdict__status">
            Boss's call: <strong>{statusLabel(resolution.final_status)}</strong>
          </div>
          <p>{resolution.summary}</p>
          {resolution.customer_message && (
            <blockquote className="verdict__reply">
              <MessageCircle size={15} aria-hidden />
              <span>{resolution.customer_message}</span>
            </blockquote>
          )}
          {resolution.risks.length > 0 && (
            <ul className="verdict__risks">
              {resolution.risks.map((r, i) => (
                <li key={i}>
                  <TriangleAlert size={13} aria-hidden /> {r}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="summary__grid">
        {AGENTS.map((meta) => {
          const a = activity.get(meta.name);
          if (!a) {
            return (
              <article key={meta.name} className="recap recap--benched" style={agentStyle(meta.name)}>
                <AgentAvatar agent={meta.name} size="sm" />
                <div>
                  <h3>{meta.label}</h3>
                  <p className="muted">{running ? "Not involved yet." : "Not needed on this ticket."}</p>
                </div>
              </article>
            );
          }
          const report = a.report && !isResolution(a.report) ? (a.report as SpecialistReport) : null;
          const summary = report?.summary ?? (isResolution(a.report) ? a.report.summary : a.lastMessage);
          return (
            <article key={meta.name} className="recap" style={agentStyle(meta.name)}>
              <AgentAvatar agent={meta.name} size="sm" />
              <div className="recap__body">
                <h3>
                  {meta.label}
                  <span className="muted">
                    {a.steps} steps · {a.tokens.toLocaleString()} tokens
                  </span>
                </h3>
                <p>{summary}</p>
                {report?.blocked && <p className="recap__blocked">Blocked: {report.blocked}</p>}
                <dl className="recap__facts">
                  {a.tools.size > 0 && (
                    <>
                      <dt>Tools</dt>
                      <dd>
                        {[...a.tools.entries()].map(([t, n]) => (
                          <span key={t} className="chip chip--tool">
                            {t}
                            {n > 1 && <span className="chip__n">×{n}</span>}
                          </span>
                        ))}
                      </dd>
                    </>
                  )}
                  {a.delegatedTo.length > 0 && (
                    <>
                      <dt>Handed to</dt>
                      <dd>
                        {a.delegatedTo.map((d) => (
                          <AgentTag key={d} agent={d} />
                        ))}
                      </dd>
                    </>
                  )}
                  {report && report.approval_requests_created.length > 0 && (
                    <>
                      <dt>Prepared</dt>
                      <dd>
                        {report.approval_requests_created.map((id) => (
                          <span key={id} className="chip">
                            request #{id}
                          </span>
                        ))}
                      </dd>
                    </>
                  )}
                </dl>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
