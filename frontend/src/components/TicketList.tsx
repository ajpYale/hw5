import { CircleCheckBig, KeyRound, LoaderCircle, ShoppingBag, Tag, type LucideIcon } from "lucide-react";
import { statusLabel } from "../format";
import type { Ticket } from "../types";

const TYPE_ICON: Record<string, LucideIcon> = {
  customer_order: ShoppingBag,
  rent_notice: KeyRound,
  price_override: Tag,
};

interface Props {
  tickets: Ticket[];
  selectedId: number | null;
  justResolved: Set<number>;
  onSelect: (id: number) => void;
}

export function TicketList({ tickets, selectedId, justResolved, onSelect }: Props) {
  const resolved = tickets.filter((t) => t.status === "resolved").length;
  return (
    <aside className="panel tickets" aria-label="Tickets">
      <header className="panel__head">
        <h2>Desk queue</h2>
        <span className="tickets__count">
          {resolved}/{tickets.length} resolved
        </span>
      </header>
      <div className="tickets__progress" aria-hidden>
        <span style={{ width: `${tickets.length ? (resolved / tickets.length) * 100 : 0}%` }} />
      </div>
      <ul className="tickets__list">
        {tickets.map((t) => {
          const Icon = TYPE_ICON[t.type] ?? ShoppingBag;
          const running = t.last_run?.status === "running";
          const state = running ? "running" : t.status;
          return (
            <li key={t.id}>
              <button
                className={[
                  "ticket",
                  `ticket--${state}`,
                  t.id === selectedId ? "ticket--selected" : "",
                  justResolved.has(t.id) ? "ticket--celebrate" : "",
                ].join(" ")}
                onClick={() => onSelect(t.id)}
                aria-pressed={t.id === selectedId}
              >
                <span className="ticket__icon">
                  <Icon size={18} aria-hidden />
                </span>
                <span className="ticket__body">
                  <span className="ticket__id">#{t.id}</span>
                  <span className="ticket__title">{t.title}</span>
                  <span className="ticket__who">{t.requester}</span>
                </span>
                <span className={`pill pill--${state}`}>
                  {running && <LoaderCircle size={12} className="spin" aria-hidden />}
                  {state === "resolved" && <CircleCheckBig size={12} aria-hidden />}
                  {running ? "Running" : state === "resolved" ? "Resolved" : "Open"}
                </span>
                {t.status === "resolved" && !running && (
                  <span className="ticket__sub">{statusLabel(t.detailed_status)}</span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
