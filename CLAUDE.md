# Trading Rules (standing, every session)

This project drives a real-money Robinhood brokerage account through the
`robinhood-trading` MCP server. These rules always apply:

- **Research is free.** Read-only tools (quotes, fundamentals, positions,
  P&L, watchlists, scans, earnings, historicals) may be used without asking.
- **Stocks only.** Never call option order tools. Option research tools are
  also off limits — this account trades equities.
- **All order placement goes through the `/trade` skill pipeline.** Never
  call `place_equity_order` outside it.
- **Explicit confirmation per order.** An order may be placed only after the
  user replies exactly `confirm` to a full read-back in the current
  conversation. Confirmation never carries over between orders or sessions.
- **$500 max per order, limit orders only.** Also machine-enforced by the
  PreToolUse hook in `.claude/hooks/guard_orders.py` — if it blocks an
  order, relay the reason and resize only if the user asks.
- **$1,500 max total order notional per trading day** (US Eastern) —
  machine-enforced by the same hook via a local ledger of approved orders.
- **Daily-loss halt:** `/trade` refuses new buys once today's realized loss
  exceeds 2% of account value, unless the user explicitly overrides (one
  order per override).
- **Never cancel or modify an order without explicit user confirmation.**
- **Ambiguous order failures:** check `get_equity_orders` before any retry;
  reuse the same `ref_id` when retrying so nothing double-submits.
- **Account selection:** the account number must be confirmed by the user
  (or already confirmed earlier in the session); never silently default
  from `get_accounts`.
- **MCP auth expiry:** on 401s from robinhood-trading tools, tell the user to
  re-authenticate via /mcp; do not retry blindly.
- **Mask account numbers everywhere they are displayed or written** — show
  only the last 4 digits (e.g. ••••7276) in chat, docs, commits, and reports.
  Full account numbers go only into tool-call parameters.

## Operation risk tiers

| Tier | Operations | Policy |
|---|---|---|
| Low (read) | quotes, fundamentals, historicals, positions, portfolio, P&L, watchlists (read), scans (read/run), earnings, orders (read), indexes, search | Use freely, no confirmation |
| Medium | create/update watchlists and scans; cancel a single order | Watchlist/scan edits only on user request; cancels need a yes/no confirmation |
| High (write) | `place_equity_order` | Only via the `/trade` pipeline: guard hook + full read-back + exact `confirm` |
| Blocked | all option order tools; market/stop orders; orders over $500 notional; orders pushing the day's approved total over $1,500 | Machine-denied by `.claude/hooks/guard_orders.py` — never attempt, never work around |
