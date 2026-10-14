import { BadgeCheck, Inbox, KeyRound, LoaderCircle, Receipt, Tag, Truck, type LucideIcon } from "lucide-react";
import { money } from "../format";
import type { Approval, ApprovalKind } from "../types";
import { AgentTag } from "./AgentAvatar";

const KIND: Record<ApprovalKind, { label: string; icon: LucideIcon }> = {
  rent: { label: "Rent payment", icon: KeyRound },
  invoice: { label: "Vendor invoice", icon: Receipt },
  purchase_order: { label: "Purchase order", icon: Truck },
  price_override: { label: "Discount", icon: Tag },
};

interface Props {
  approvals: Approval[];
  approver: string;
  busyId: number | null;
  onApprove: (a: Approval) => void;
}

export function ApprovalQueue({ approvals, approver, busyId, onApprove }: Props) {
  const total = approvals.filter((a) => a.moves_cash).reduce((s, a) => s + a.amount, 0);
  return (
    <aside className="panel approvals" aria-label="Pending approvals">
      <header className="panel__head">
        <h2>Needs your sign-off</h2>
        {approvals.length > 0 && <span className="count-badge">{approvals.length}</span>}
      </header>
      <p className="approvals__note">
        Agents only <em>prepare</em> these. Cash moves when you approve.
      </p>
      {approvals.length === 0 ? (
        <div className="empty empty--inbox">
          <Inbox size={28} aria-hidden />
          Nothing waiting on you.
        </div>
      ) : (
        <>
          <ul className="approvals__list">
            {approvals.map((a) => {
              const { label, icon: Icon } = KIND[a.kind];
              const reason = a.details.split(" Reason: ");
              return (
                <li key={a.id} className={`approval approval--${a.kind}`}>
                  <div className="approval__top">
                    <span className="approval__icon">
                      <Icon size={16} aria-hidden />
                    </span>
                    <div>
                      <div className="approval__kind">{label}</div>
                      <div className="approval__ticket">
                        Request #{a.id} · Ticket #{a.ticket_id}
                      </div>
                    </div>
                    <div className="approval__amount">{money(a.amount)}</div>
                  </div>
                  <p className="approval__details">{reason[0]}</p>
                  {reason[1] && <p className="approval__reason">“{reason[1]}”</p>}
                  <div className="approval__foot">
                    <AgentTag agent={a.requested_by} />
                    {!a.moves_cash && <span className="muted small">No cash moves</span>}
                    <button
                      className="btn btn--approve"
                      onClick={() => onApprove(a)}
                      disabled={busyId !== null || !approver.trim()}
                      title={approver.trim() ? `Approve as ${approver}` : "Enter your name in the header first"}
                    >
                      {busyId === a.id ? (
                        <LoaderCircle size={15} className="spin" aria-hidden />
                      ) : (
                        <BadgeCheck size={15} aria-hidden />
                      )}
                      Approve
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
          <div className="approvals__total">
            Cash out if all approved <strong>{money(total)}</strong>
          </div>
        </>
      )}
    </aside>
  );
}
