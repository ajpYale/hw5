import type { CSSProperties } from "react";
import { AGENTS } from "../agents";

const PIECES = Array.from({ length: 36 }, (_, i) => ({
  angle: (360 / 36) * i + (i % 3) * 7,
  distance: 120 + ((i * 37) % 110),
  color: AGENTS[i % AGENTS.length].color,
  delay: (i % 6) * 25,
  size: 6 + (i % 4) * 2,
}));

/** A stamp plus a burst in the five agent colors: the team finished together. */
export function Celebration({ ticketId }: { ticketId: number }) {
  return (
    <div className="celebrate" aria-live="polite">
      <div className="celebrate__burst" aria-hidden>
        {PIECES.map((p, i) => (
          <span
            key={i}
            style={
              {
                "--angle": `${p.angle}deg`,
                "--distance": `${p.distance}px`,
                "--delay": `${p.delay}ms`,
                "--size": `${p.size}px`,
                background: p.color,
              } as CSSProperties
            }
          />
        ))}
      </div>
      <div className="celebrate__stamp">
        Resolved
        <small>Ticket #{ticketId}</small>
      </div>
    </div>
  );
}
