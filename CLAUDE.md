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
- **Never cancel or modify an order without explicit user confirmation.**
- **Ambiguous order failures:** check `get_equity_orders` before any retry;
  reuse the same `ref_id` when retrying so nothing double-submits.
- **Account selection:** the account number must be confirmed by the user
  (or already confirmed earlier in the session); never silently default
  from `get_accounts`.
- **MCP auth expiry:** on 401s from robinhood-trading tools, tell the user to
  re-authenticate via /mcp; do not retry blindly.
