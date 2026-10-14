import { Activity, CircleCheckBig, LoaderCircle, Play, RotateCcw, Store, User } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, API_URL } from "./api";
import { AgentFloor } from "./components/AgentFloor";
import { AgentSummary } from "./components/AgentSummary";
import { ApprovalQueue } from "./components/ApprovalQueue";
import { CashTile } from "./components/CashTile";
import { Celebration } from "./components/Celebration";
import { TicketList } from "./components/TicketList";
import { Timeline } from "./components/Timeline";
import { activityByAgent, deskDate, handoffs, humanize, isResolution, latestSession, money, statusLabel } from "./format";
import { useInterval, useLocalStorage } from "./hooks";
import type { AgentEvent, Approval, Cash, Ticket } from "./types";

const FAST_POLL = 1200; // while the selected ticket is running
const SLOW_POLL = 5000; // tickets, approvals, cash otherwise

interface Toast {
  id: number;
  tone: "good" | "bad" | "info";
  text: string;
}

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  // ?ticket=102 deep-links straight to a ticket (handy for sharing and screenshots).
  const [selectedId, setSelectedId] = useState<number | null>(() => {
    const id = Number(new URLSearchParams(location.search).get("ticket"));
    return Number.isInteger(id) && id > 0 ? id : null;
  });
  useEffect(() => {
    if (selectedId === null) return;
    const url = new URL(location.href);
    url.searchParams.set("ticket", String(selectedId));
    history.replaceState(null, "", url);
  }, [selectedId]);
  const [eventsByTicket, setEventsByTicket] = useState<Record<number, AgentEvent[]>>({});
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [cash, setCash] = useState<Cash | null>(null);
  const [online, setOnline] = useState(true);
  const [approver, setApprover] = useLocalStorage("desk.approver", "");
  const [busyApproval, setBusyApproval] = useState<number | null>(null);
  const [starting, setStarting] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [celebrating, setCelebrating] = useState<number | null>(null);
  const [justResolved, setJustResolved] = useState<Set<number>>(new Set());
  const [toasts, setToasts] = useState<Toast[]>([]);
  const prevTickets = useRef<Map<number, Ticket>>(new Map());

  const toast = useCallback((tone: Toast["tone"], text: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, tone, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000);
  }, []);

  const selected = tickets.find((t) => t.id === selectedId) ?? null;
  const selectedRunning = selected?.last_run?.status === "running";

  // ---- data loading ---------------------------------------------------------

  const eventsByTicketRef = useRef(eventsByTicket);
  eventsByTicketRef.current = eventsByTicket;

  /** Full load, or only events newer than the last one we have (the API's `since`). */
  const loadEvents = useCallback(async (ticketId: number, incremental: boolean) => {
    const existing = eventsByTicketRef.current[ticketId];
    const since = incremental && existing?.length ? existing[existing.length - 1].id : undefined;
    const { events } = await api.events(ticketId, since);
    setEventsByTicket((all) => {
      const current = all[ticketId] ?? [];
      if (since === undefined) return { ...all, [ticketId]: events };
      const seen = new Set(current.map((e) => e.id)); // overlapping polls can't double-add
      return { ...all, [ticketId]: [...current, ...events.filter((e) => !seen.has(e.id))] };
    });
  }, []);

  const celebrate = useCallback((ticketId: number) => {
    setCelebrating(ticketId);
    setJustResolved((s) => new Set(s).add(ticketId));
    setTimeout(() => setCelebrating((c) => (c === ticketId ? null : c)), 2600);
    setTimeout(
      () =>
        setJustResolved((s) => {
          const next = new Set(s);
          next.delete(ticketId);
          return next;
        }),
      4000,
    );
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [t, a, c] = await Promise.all([api.tickets(), api.approvals(), api.cash()]);
      setOnline(true);
      setApprovals(a);
      setCash(c);
      setTickets(t);
      setSelectedId((id) => id ?? t[0]?.id ?? null);

      // A run that just finished: pull its last events and celebrate if resolved.
      for (const ticket of t) {
        const before = prevTickets.current.get(ticket.id);
        const wasRunning = before?.last_run?.status === "running";
        const finished = wasRunning && ticket.last_run?.status !== "running";
        if (!finished) continue;
        await loadEvents(ticket.id, true);
        if (ticket.last_run?.status === "failed") {
          toast("bad", `Ticket #${ticket.id} run failed: ${ticket.last_run.error}`);
        } else if (ticket.status === "resolved") {
          celebrate(ticket.id);
          toast("good", `Ticket #${ticket.id} resolved: ${statusLabel(ticket.detailed_status)}`);
        }
      }
      prevTickets.current = new Map(t.map((x) => [x.id, x]));
    } catch {
      setOnline(false);
    }
  }, [celebrate, loadEvents, toast]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (selectedId !== null) void loadEvents(selectedId, false).catch(() => setOnline(false));
  }, [selectedId, loadEvents]);

  useInterval(() => void refresh(), selectedRunning || tickets.some((t) => t.last_run?.status === "running") ? FAST_POLL : SLOW_POLL);
  useInterval(
    () => {
      if (selectedId !== null) void loadEvents(selectedId, true).catch(() => setOnline(false));
    },
    selectedRunning ? FAST_POLL : null,
  );

  // ---- actions ----------------------------------------------------------------

  async function run() {
    if (!selected) return;
    setStarting(true);
    try {
      const started = await api.run(selected.id);
      toast("info", `Boss picked up ticket #${selected.id}`);
      setTickets((all) =>
        all.map((t) =>
          t.id === selected.id
            ? {
                ...t,
                last_run: {
                  ticket_id: t.id,
                  session_id: started.session_id,
                  status: "running",
                  started_at: new Date().toISOString(),
                  finished_at: null,
                  error: null,
                  result: null,
                },
              }
            : t,
        ),
      );
    } catch (e) {
      toast("bad", e instanceof ApiError ? e.message : "Couldn't reach the API.");
    } finally {
      setStarting(false);
    }
  }

  async function approve(a: Approval) {
    setBusyApproval(a.id);
    try {
      const result = await api.approve(a.id, approver.trim());
      toast(
        "good",
        result.cash_moved
          ? `Approved #${a.id}: ${money(a.amount)} left checking`
          : `Approved #${a.id}: discount is now final (no cash moved)`,
      );
      await refresh();
    } catch (e) {
      toast("bad", e instanceof ApiError ? e.message : "Couldn't reach the API.");
    } finally {
      setBusyApproval(null);
    }
  }

  async function reset() {
    if (!confirmReset) {
      setConfirmReset(true);
      setTimeout(() => setConfirmReset(false), 4000);
      return;
    }
    setConfirmReset(false);
    try {
      await api.reset();
      setEventsByTicket({});
      prevTickets.current = new Map();
      toast("info", "Desk reset to the original data");
      await refresh();
    } catch (e) {
      toast("bad", e instanceof ApiError ? e.message : "Couldn't reach the API.");
    }
  }

  // ---- derived view of the selected ticket -------------------------------------

  const sessionEvents = useMemo(() => {
    if (!selected) return [];
    const events = eventsByTicket[selected.id] ?? [];
    // Show the current run, or the last one if the ticket has been worked.
    const session =
      selected.last_run?.session_id ?? (selected.status === "resolved" ? latestSession(events) : null);
    return session ? events.filter((e) => e.session_id === session) : [];
  }, [selected, eventsByTicket]);

  const activity = useMemo(() => activityByAgent(sessionEvents), [sessionEvents]);
  const hops = useMemo(() => handoffs(sessionEvents), [sessionEvents]);
  const resolution = useMemo(() => {
    const boss = activity.get("boss")?.report;
    return isResolution(boss) && sessionEvents.some((e) => e.agent === "boss" && e.depth === 0 && e.kind === "final")
      ? boss
      : (selected?.last_run?.result ?? null);
  }, [activity, sessionEvents, selected]);
  const runTokens = sessionEvents.reduce((s, e) => s + e.tokens, 0);

  return (
    <div className="desk">
      <header className="topbar">
        <div className="brand">
          <span className="brand__mark">
            <Store size={20} aria-hidden />
          </span>
          <div>
            <h1>Campus Customs</h1>
            <p>
              Ops Desk · {cash ? deskDate(cash.as_of) : "…"}
              <span className={`status-dot${online ? "" : " status-dot--off"}`} title={API_URL} />
              {online ? "API connected" : "API offline: start uvicorn on :8000"}
            </p>
          </div>
        </div>
        <CashTile cash={cash} />
        <div className="topbar__actions">
          <label className="approver">
            <User size={14} aria-hidden />
            <span className="sr-only">Approving as</span>
            <input
              value={approver}
              onChange={(e) => setApprover(e.target.value)}
              placeholder="Your name (approver)"
              aria-label="Approving as"
            />
          </label>
          <button className={`btn btn--ghost${confirmReset ? " btn--danger" : ""}`} onClick={reset}>
            <RotateCcw size={15} aria-hidden />
            {confirmReset ? "Click again to reset" : "Reset"}
          </button>
        </div>
      </header>

      <main className="layout">
        <TicketList tickets={tickets} selectedId={selectedId} justResolved={justResolved} onSelect={setSelectedId} />

        <div className="stage">
          {selected ? (
            <>
              <section className={`panel brief${selected.status === "resolved" ? " brief--resolved" : ""}`}>
                {celebrating === selected.id && <Celebration ticketId={selected.id} />}
                <div className="brief__text">
                  <span className="brief__eyebrow">
                    Ticket #{selected.id} · {humanize(selected.type)}
                  </span>
                  <h2>{selected.title}</h2>
                  <p>
                    From <strong>{selected.requester}</strong> ·{" "}
                    {selectedRunning ? "The team is on it" : statusLabel(selected.detailed_status)}
                    {runTokens > 0 && (
                      <>
                        {" · "}
                        <span className="muted">
                          <Activity size={12} aria-hidden /> {sessionEvents.length} steps, {runTokens.toLocaleString()} tokens
                        </span>
                      </>
                    )}
                  </p>
                </div>
                {selected.status === "resolved" && !selectedRunning ? (
                  <div className="brief__done">
                    <CircleCheckBig size={22} aria-hidden />
                    Resolved
                    <button className="btn btn--ghost btn--small" onClick={run} disabled={starting}>
                      Run again
                    </button>
                  </div>
                ) : (
                  <button className="btn btn--run" onClick={run} disabled={selectedRunning || starting || !online}>
                    {selectedRunning || starting ? (
                      <LoaderCircle size={18} className="spin" aria-hidden />
                    ) : (
                      <Play size={18} aria-hidden />
                    )}
                    {selectedRunning ? "Running…" : "Run"}
                  </button>
                )}
              </section>

              <AgentFloor activity={activity} hops={hops} running={selectedRunning} hasSession={sessionEvents.length > 0} />

              <div className="stage__split">
                <Timeline events={sessionEvents} running={selectedRunning} />
                {sessionEvents.length > 0 && <AgentSummary activity={activity} resolution={resolution} running={selectedRunning} />}
              </div>
            </>
          ) : (
            <p className="empty">Loading tickets…</p>
          )}
        </div>

        <ApprovalQueue approvals={approvals} approver={approver} busyId={busyApproval} onApprove={approve} />
      </main>

      <div className="toasts" role="status">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast--${t.tone}`}>
            {t.text}
          </div>
        ))}
      </div>
    </div>
  );
}
