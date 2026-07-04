---
name: brief
description: Pre-market or intraday research briefing - index levels, movers among held and watched stocks, upcoming earnings. Use when the user asks for a market brief, morning rundown, or what's moving today.
---

# Market briefing

Read-only. Universe = held positions (`get_equity_positions`) plus every
symbol on the user's watchlists (`get_watchlists` → `get_watchlist_items`).

1. Indexes: `get_indexes` → `get_index_quotes` for S&P 500, Nasdaq, Dow.
2. Quotes for the whole universe via `get_equity_quotes` (batch).
3. Earnings: `get_earnings_calendar`, filtered to the universe, next 7
   days; include `get_earnings_results` for any that reported today.
4. Output order: (a) anything urgent — halted names, moves over ±5%,
   earnings today; (b) index levels; (c) movers sorted by absolute %
   change, held names marked; (d) earnings calendar.
5. Keep it scannable — tables for quotes, one line per earnings event.

Never place, modify, or cancel anything from this skill.
