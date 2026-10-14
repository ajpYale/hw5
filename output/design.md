# Campus Customs Ops Desk: Design Notes

The frontend (`frontend/`, React + Vite + TypeScript) is the screen a shop manager keeps open during a shift. It answers four questions at a glance: *what's in the queue, who's working on it right now, what do they need from me, and how much cash do I have.* Every design choice serves one of those.

## Layout

The desk is three columns under a sticky top bar, ordered the way work flows: **intake → work → sign-off**.

| Area | What it holds | Why it's there |
|---|---|---|
| **Top bar** | Brand and business date (`desk.date_today`, not the wall clock), the **checking balance** in the center, the approver name field, and Reset | Cash is the one number the manager should never have to look for, so it sits dead center in the bar that never scrolls away. |
| **Left: Desk queue** | The three tickets, each with a type icon, requester, and an Open / Running / Resolved pill. A thin progress bar shows "x/3 resolved". | Reads like an inbox. The progress bar turns clearing the queue into a visible goal. |
| **Center: the stage** | (1) The ticket brief with a big **Run** button. (2) The **hand-off relay**. (3) The **agent floor**: five agent cards. (4) **Live activity** feed and **Who did what** summary side by side. | Top to bottom it goes from what you're looking at, to how it flowed, to who's doing what, to the detail. |
| **Right: Needs your sign-off** | Pending payments, purchase orders and discounts, each with an Approve button and a running "cash out if all approved" total | It's the one place a human has to act, so it's its own column and stays in view while the agents work. |

The page polls the API every 1.2s while a ticket is running and every 5s otherwise. Events are fetched incrementally with `since=<last event id>`, so the feed only ever appends.

## How agents are distinguished

Each agent has three identity cues that agree everywhere they appear: the card, the avatar, feed rows, hand-off arrows, the summary and approval tags.

| Agent | Color | Icon | Why |
|---|---|---|---|
| Boss | Gold `#f5b83d` | Crown | The coordinator. Gold is also the brand and Run-button color, because the Boss is who you're asking to start. |
| Inventory | Teal `#2dd4bf` | Package | Calm and physical: shelves and boxes. |
| Accounting | Violet `#a78bfa` | Calculator | Distinct from the money-state colors (green and red), so "Accounting did something" never reads as "cash moved". |
| Facilities | Coral `#fb8c5a` | Building | Warm, for the building and the lease. |
| Customer Service | Sky blue `#60a5fa` | Headset | Friendly and conversational. The customer-reply quote uses the same blue. |

- **One CSS variable per agent.** Every agent element sets `--agent`, and borders, glows, tints and text derive from it with `color-mix()`. That keeps the five identities consistent without five copies of the styles.
- **The colors avoid green and red on purpose.** Those two are reserved for *resolved* and *cash leaving*, so neither ever gets confused with an agent.
- **Avatars are rounded squares with a tinted fill and a colored outline,** so they read on the dark background and still work for color-blind users because each also has a unique icon.
- **Live state:** the agent that's working right now gets a pulsing ring on its avatar, a lifted card and a colored glow. Its status dot blinks. Agents that finish show "Reported" with a green dot. Agents the ticket never needed fade and desaturate as "Not needed". That shows at a glance that the Boss didn't just call everyone, which was a goal of the plan in `desk_tickets.html`.
- **Each agent card also shows** who called it ("from Boss"), its latest message, the tool chips it has called (with ×counts), and colored hand-off chips for anyone it delegated to.

## Showing hand-offs

- **Hand-off relay:** a strip of numbered hops such as `1 Ticket → Boss`, `2 Boss → Facilities`, `3 Boss → Accounting`. Each hop is drawn as avatar → gradient arrow → avatar, and the arrow blends from the sender's color to the receiver's. The newest hop's arrow animates while the run is live. Parallel hand-offs (the Boss sending to Accounting and Inventory at once on 103) show as consecutive hops.
- **Live activity feed:** newest first. Each row has the agent's color rail and is indented by delegation depth, so a nested call (Inventory → Accounting on 101) is visibly *inside* its caller. Final reports are tinted and tagged "Report", and errors are red.
- **Detecting hand-offs correctly:** the hops are inferred from the *first* event of each agent run, not from the caller's delegate record. That record is only written after the sub-agent finishes, so using it would show hand-offs late and out of order.

## Resolved tickets

"Resolved" on the board means **the agent team has finished its work**. In the DB terms the API uses, `open`/`in_progress` count as open and everything else as resolved. A sub-line says what it's waiting on, for example "Awaiting your approval". When you approve the last pending request, the API moves the ticket to **Fully resolved**.

The moment a run finishes:

- **Stamp:** a green **RESOLVED** stamp thumps onto the ticket brief (it scales down from 2.2× with a slight overshoot, rotated −6°, like a rubber stamp).
- **Confetti:** a burst of confetti in the *five agent colors* fires behind it. The team finished together.
- **Queue card:** the ticket card pops with a green pulse, its left edge and icon turn green, and the "x/3 resolved" bar grows.
- **Toast:** a toast confirms it, for example "Ticket #103 resolved: Awaiting your approval".

The brief then keeps a calm green "✓ Resolved" with a small "Run again" button. The celebration is short (about 2.6s) and stays out of the way.

## Cash

The balance is the largest text on the page: 34px JetBrains Mono with tabular numerals, so digits don't jiggle while they change.

- **When cash leaves** (only via Approve):
  - the number **counts down** to the new balance over about 1.1s (ease-out)
  - the tile flashes **red** with a glow and a short shake
  - a red **"−$2,400.00"** floats out beside it and fades
- **Under the balance:** *Pending* and *If all approved*. If everything pending would overdraw checking (as with all three tickets: $3,504 pending against $3,400), *If all approved* turns amber with a warning icon. The manager sees the conflict before clicking anything.
- **Approval cards:** each shows the amount in mono, what it's for, the agent's own reason in quotes, and which agent prepared it. Discounts say "No cash moves", and approving one gives no red flash, because nothing left the account.
- **Approver name required:** approving requires a name in the top bar, since every payment records who approved it. The Approve button stays disabled until it's filled.

## Palette and type

- **Background:** ink navy `#0b1020` with a faint 32px grid and a soft blue glow at the top. It reads as a night-shift control room, keeps long sessions easy on the eyes, and gives the agent colors maximum contrast.
- **Surfaces:** stepped navies (`#111a2e` → `#17223b` → `#1e2b48`) with 1px borders, so panels separate without heavy shadows.
- **Semantic colors, used for nothing else:** green `#34d399` means resolved or approve, red `#ff5d73` means cash leaving or errors, amber `#fbbf24` means a warning. Gold is the brand and the Boss. The Yale blue `#2a5aa8` → `#00356b` appears only in the logo mark.
- **Type:**
  - **Space Grotesk:** headings and labels, for a slightly technical, "ops" character.
  - **Inter:** body text, for readability at small sizes.
  - **JetBrains Mono:** everything that's *data*: money, tool names, ids and timestamps. Mono for data means a tool name like `check_invoice` never looks like prose.
  - All three fonts are bundled through `@fontsource`, so the desk works offline.

## Why it's pleasant to use

- **Nothing to hunt for:**
  - Cash stays fixed at the center of the top bar.
  - Sign-offs stay in the right column.
  - The selected ticket fills the middle.
- **It narrates itself:** the relay, the pulsing live agent and the feed mean you can watch the team think without reading logs, and *Who did what* gives the recap when it's over.
- **Trust is visible:**
  - **Prepared vs. moved:** the approvals column says outright that agents only *prepare* and that cash moves when you approve.
  - **Reasons shown:** every request shows the agent's reasoning.
  - **Overdraft warnings:** a pending overdraft is flagged in amber before you approve.
- **Feedback is proportional:** a big moment (a ticket resolved) gets a stamp and confetti, a money moment gets a red count-down, and routine updates just slide into the feed.
- **Safe defaults:**
  - **Reset:** needs a second click within 4 seconds.
  - **Approve:** stays disabled until an approver is named.
  - **API offline:** the status dot turns red and says how to fix it.
  - **Reduced motion:** with `prefers-reduced-motion` set, animations are turned off. The cash number still updates; it just doesn't animate.
