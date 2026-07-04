---
name: portfolio
description: Review the Robinhood portfolio - positions, allocation, realized and unrealized P&L, trade history. Use when the user asks how their portfolio, positions, or P&L are doing.
---

# Portfolio & P&L review

Read-only. Default period for realized P&L: year to date; honor any period
the user names.

1. Pull `get_portfolio`, `get_equity_positions`, `get_realized_pnl`, and
   `get_pnl_trade_history` (for the period).
2. Build a holdings table: symbol, shares, average cost, market value,
   unrealized P&L ($ and %), and % of portfolio.
3. Flag concentration: any single position over 20% of portfolio value.
4. Biggest winners and losers, unrealized and realized.
5. Close with a one-paragraph plain-English summary: total value, day
   change, what most needs attention.

Never place, modify, or cancel anything from this skill — hand trade ideas
to `/trade`.
