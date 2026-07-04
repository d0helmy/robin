---
name: brief
description: Pre-market or intraday research briefing - index levels, movers among held and watched stocks, upcoming earnings. Use when the user asks for a market brief, morning rundown, or what's moving today.
---

# Market briefing

Read-only. Universe = held positions (`get_equity_positions`) plus every
symbol on the user's watchlists (`get_watchlists` → `get_watchlist_items`).

1. Indexes: `get_indexes` → `get_index_quotes` for S&P 500, Nasdaq, Dow.
2. Quotes for the whole universe via ONE `get_equity_quotes` call with all
   symbols — do not split into batches of 20. Above 20 symbols the response
   omits the official-close pairing; that's fine: compute day change from
   each quote's `adjusted_previous_close`, which is always present.
3. Earnings: `get_earnings_calendar`, filtered to the universe, next 7
   days; include `get_earnings_results` for any that reported today.
4. Why-it-moved (only when warranted): for names moving more than ±5% or
   reporting today, run one WebSearch per name for fresh headlines and add
   a one-line reason next to the mover. Skip on quiet days; never let news
   lookups more than double the briefing time.
5. Output order: (a) anything urgent — halted names, moves over ±5%,
   earnings today; (b) index levels; (c) movers sorted by absolute %
   change, held names marked, with why-it-moved notes; (d) earnings
   calendar.
6. Keep it scannable — tables for quotes, one line per earnings event.

Never place, modify, or cancel anything from this skill.
