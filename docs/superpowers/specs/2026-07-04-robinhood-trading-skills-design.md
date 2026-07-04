# Robinhood Trading Skills & Guardrails — Design

**Date:** 2026-07-04
**Status:** Approved by user (approach B)

## Purpose

Set up Claude Code skills and enforcement for trading through the connected
`robinhood-trading` MCP server. Claude researches freely; every order requires
explicit user confirmation, with hard mechanical guardrails on order placement.

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Agency | Analysis free; every order placement individually confirmed by the user |
| Instruments | Stocks only — option order tools are blocked outright |
| Workflows | `/portfolio`, `/brief`, `/trade`, `/scan` |
| Guardrails | $500 max per order, limit orders only, full read-back + explicit "confirm" |
| Enforcement | Prompt-level rules **plus** a PreToolUse guard hook (approach B) |

## File layout

```
/Users/dia/Documents/robinh/
├── CLAUDE.md                          # standing trading rules, loaded every session
└── .claude/
    ├── settings.json                  # registers the PreToolUse guard hook
    ├── hooks/
    │   └── guard_orders.py            # hard enforcement of order rules
    └── skills/
        ├── portfolio/SKILL.md         # /portfolio
        ├── brief/SKILL.md             # /brief
        ├── trade/SKILL.md             # /trade
        └── scan/SKILL.md              # /scan
```

## Component: skills

### /portfolio — portfolio & P&L review
- Tools: `get_portfolio`, `get_equity_positions`, `get_realized_pnl`,
  `get_pnl_trade_history`.
- Output: holdings table (shares, cost basis, market value, unrealized P&L),
  allocation/concentration flags (any position >20% of portfolio value),
  biggest winners/losers, realized P&L for the requested period
  (default: year to date).

### /brief — pre-market research briefing
- Tools: `get_watchlists`, `get_watchlist_items`, `get_equity_quotes`,
  `get_index_quotes`, `get_indexes`, `get_earnings_calendar`,
  `get_equity_positions`.
- Output: index levels, movers among held + watched names (sorted by absolute
  % change), upcoming earnings (next 7 days) filtered to those names,
  anything needing attention first.

### /trade — trade preparation & execution
Strict pipeline; no step may be skipped:
1. Quote + tradability check (`get_equity_quotes`, `get_equity_tradability`).
2. Context: current position in the ticker, buying power (`get_equity_positions`,
   `get_portfolio`).
3. Construct a **limit** order (never market).
4. `review_equity_order` for Robinhood's own pre-flight response.
5. **Read-back** to the user: ticker, side, shares, limit price, estimated
   cost, buying-power impact.
6. User must reply with the word **confirm** (exactly; any other reply
   aborts). Confirmation applies to one order only and never carries over.
7. `place_equity_order`.
8. Verify via `get_equity_orders`; report order state (filled / pending /
   rejected) to the user.

Also handles: order status checks (`get_equity_orders`) and cancellations
(`cancel_equity_order`) — cancels require a lighter yes/no confirmation.

### /scan — screening
- Tools: `get_scans`, `create_scan`, `run_scan`, `update_scan_config`,
  `update_scan_filters`, `search`, `get_equity_quotes`,
  `get_equity_fundamentals`.
- Output: candidate list (top hits enriched with price, % change, market cap,
  P/E), formatted so a candidate can be handed straight to `/trade`.

## Component: guard hook (hard enforcement)

`PreToolUse` hook registered in `.claude/settings.json` with matcher
`mcp__robinhood-trading__place_equity_order|mcp__robinhood-trading__place_option_order`.

`guard_orders.py` reads the hook JSON from stdin and **denies** the call
(exit 2, reason on stderr) unless all of the following hold:

1. Tool is `place_equity_order` — `place_option_order` is denied
   unconditionally (stocks only).
2. Order type is `limit` (market and any other types denied).
3. `limit_price × quantity ≤ 500` (USD). Notional-only orders (dollar-based)
   are denied unless the notional amount is ≤ 500 and a limit price is present.
4. Malformed/unparseable input → deny (fail closed).

The hook runs outside the model, so rules 1–3 cannot be violated by a model
mistake. The read-back/confirm rule stays at the skill level: a hook cannot
verify conversation content, and that rule exists to keep the user in the
loop, not to validate mechanics.

The exact parameter names for `place_equity_order` (e.g. `order_type` vs
`type`, `limit_price` vs `price`) will be confirmed against the live tool
schema during implementation, before the hook is finalized. The hook must
key off the real schema, not guesses.

## Component: CLAUDE.md

Standing rules for every session in this project:
- Research/read-only tools may be used freely.
- Stocks only; option order tools are off limits.
- All order placement goes through the `/trade` pipeline.
- Never place, cancel, or modify an order without explicit user confirmation
  in this conversation turn.
- $500 max per order; limit orders only (also machine-enforced by the hook).
- If the guard hook blocks an order, explain why; resize only if the user asks.

## Error handling

- Hook block → relay the reason to the user; do not silently retry or resize.
- Ambiguous failure from `place_equity_order` (timeout, 5xx) → check
  `get_equity_orders` for the order before any retry, so an order is never
  double-submitted.
- MCP auth expiry (401s) → tell the user to re-authenticate via `/mcp`.

## Testing

1. Unit-test the hook script by piping fake hook payloads: valid limit order
   under cap (allow), market order (deny), over-cap limit order (deny),
   option order (deny), malformed JSON (deny).
2. Verify hook registration fires on a real `review_equity_order` →
   *stop before placement* dry run of `/trade`.
3. Exercise `/portfolio`, `/brief`, `/scan` end-to-end (all read-only).
4. Optional live test: one real user-confirmed order well under the cap.

## Out of scope (YAGNI)

- Options workflows, autonomous/scheduled trading, price alerts, tax-lot
  analysis, multi-account support. Any of these can be a later spec.
