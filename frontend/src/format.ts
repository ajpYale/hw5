import type { AgentEvent, AgentName, TicketResolution } from "./types";

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
export const money = (n: number) => usd.format(n);

export const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });

export const deskDate = (isoDate: string) =>
  new Date(`${isoDate}T12:00:00`).toLocaleDateString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });

export const humanize = (s: string) => s.replace(/_/g, " ");

const STATUS_LABEL: Record<string, string> = {
  open: "Open",
  in_progress: "In progress",
  waiting_on_approval: "Awaiting your approval",
  waiting_on_customer: "Waiting on customer",
  waiting_on_vendor: "Waiting on vendor",
  resolved: "Fully resolved",
};
export const statusLabel = (s: string) => STATUS_LABEL[s] ?? humanize(s);

/** The newest session id among a ticket's events (events arrive oldest-first). */
export function latestSession(events: AgentEvent[]): string | null {
  return events.length ? events[events.length - 1].session_id : null;
}

export interface Hop {
  from: AgentName | "ticket";
  to: AgentName;
  eventId: number;
}

/**
 * Hand-offs in the order they happened. A delegated agent's own steps are
 * logged before the delegating step completes, so a hop is detected the first
 * time an agent run shows up (agent + depth + caller), not from the caller's
 * `delegated_to` record.
 */
export function handoffs(events: AgentEvent[]): Hop[] {
  const hops: Hop[] = [];
  const active = new Set<string>();
  for (const e of events) {
    const key = `${e.agent}@${e.depth}<${e.delegated_by ?? "ticket"}`;
    if (!active.has(key)) {
      active.add(key);
      hops.push({ from: e.delegated_by ?? "ticket", to: e.agent, eventId: e.id });
    }
    if (e.kind !== "step") active.delete(key);
  }
  return hops;
}

export type AgentState = "idle" | "working" | "done" | "error";

export interface AgentActivity {
  state: AgentState;
  steps: number;
  tokens: number;
  tools: Map<string, number>;
  delegatedTo: AgentName[];
  calledBy: (AgentName | "ticket")[];
  lastMessage: string | null;
  report: AgentEvent["result"];
  lastEventId: number;
}

export function activityByAgent(events: AgentEvent[]): Map<AgentName, AgentActivity> {
  const out = new Map<AgentName, AgentActivity>();
  const hops = handoffs(events);
  for (const e of events) {
    const a: AgentActivity = out.get(e.agent) ?? {
      state: "idle",
      steps: 0,
      tokens: 0,
      tools: new Map(),
      delegatedTo: [],
      calledBy: [],
      lastMessage: null,
      report: null,
      lastEventId: -1,
    };
    a.steps += 1;
    a.tokens += e.tokens;
    a.lastEventId = e.id;
    for (const t of e.tools_used) {
      if (t !== "delegate") a.tools.set(t, (a.tools.get(t) ?? 0) + 1);
    }
    a.lastMessage = e.message;
    if (e.kind === "final") {
      a.state = "done";
      a.report = e.result;
    } else if (e.kind === "error") {
      a.state = "error";
    } else {
      a.state = "working";
    }
    out.set(e.agent, a);
  }
  for (const h of hops) {
    const target = out.get(h.to);
    if (target && !target.calledBy.includes(h.from)) target.calledBy.push(h.from);
    if (h.from !== "ticket") {
      const caller = out.get(h.from);
      if (caller && !caller.delegatedTo.includes(h.to)) caller.delegatedTo.push(h.to);
    }
  }
  return out;
}

export const isResolution = (r: AgentEvent["result"] | undefined): r is TicketResolution =>
  !!r && "final_status" in r;
