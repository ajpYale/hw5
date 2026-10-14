import { TriangleAlert, Wallet } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useAnimatedNumber } from "../hooks";
import { money } from "../format";
import type { Cash } from "../types";

interface Drop {
  id: number;
  amount: number;
}

export function CashTile({ cash }: { cash: Cash | null }) {
  const balance = cash?.balance ?? null;
  const shown = useAnimatedNumber(balance);
  const previous = useRef<number | null>(balance);
  const [drops, setDrops] = useState<Drop[]>([]);
  const [dropping, setDropping] = useState(false);

  useEffect(() => {
    const before = previous.current;
    previous.current = balance;
    if (before === null || balance === null || balance >= before) return;
    const drop = { id: Date.now(), amount: before - balance };
    setDrops((d) => [...d, drop]);
    setDropping(true);
    const settle = setTimeout(() => setDropping(false), 1400);
    const clear = setTimeout(() => setDrops((d) => d.filter((x) => x.id !== drop.id)), 2600);
    return () => {
      clearTimeout(settle);
      clearTimeout(clear);
    };
  }, [balance]);

  const overcommitted = cash ? cash.balance_if_all_pending_approved < 0 : false;

  return (
    <section className={`cash${dropping ? " cash--drop" : ""}`} aria-label="Checking balance">
      <div className="cash__label">
        <Wallet size={15} aria-hidden /> Checking
      </div>
      <div className="cash__amount" aria-live="polite">
        {shown === null ? "—" : money(shown)}
        {drops.map((d) => (
          <span key={d.id} className="cash__delta" aria-hidden>
            −{money(d.amount)}
          </span>
        ))}
      </div>
      {cash && (
        <div className="cash__meta">
          <span>
            Pending <strong>{money(cash.pending_outflow)}</strong>
          </span>
          <span className={overcommitted ? "cash__warn" : undefined}>
            {overcommitted && <TriangleAlert size={13} aria-hidden />}
            If all approved <strong>{money(cash.balance_if_all_pending_approved)}</strong>
          </span>
        </div>
      )}
    </section>
  );
}
