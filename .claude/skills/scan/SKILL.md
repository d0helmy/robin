---
name: scan
description: Create and run Robinhood market scans to surface candidate stocks (momentum, volume, sector screens). Use when the user wants to screen for stocks, find candidates, or run/modify a scan.
---

# Scans & screening

Read/write on scans only — never on orders.

1. `get_scans` first; reuse or update an existing scan
   (`update_scan_config`, `update_scan_filters`) before creating a new one
   with `create_scan`.
2. `run_scan` and take the top 10 hits.
3. Enrich each hit: `get_equity_quotes` (price, % change) and
   `get_equity_fundamentals` (market cap, P/E).
4. Output a candidate table: symbol, price, day %, market cap, P/E, and
   which filter it tripped. End with: "To act on one, run `/trade <symbol>`."

Never place, modify, or cancel orders from this skill.
