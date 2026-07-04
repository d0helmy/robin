---
name: journal
description: Record trade theses and review outcomes later - a lightweight trading journal. Use when the user wants to journal a trade, record why they entered, review past trades, or ask what they can learn from their trading history.
---

# Trade journal

Local-only: entries live in `journal/` (git-ignored, never pushed). Never
place, modify, or cancel anything from this skill.

## Recording a trade (at or near entry time)

1. Gather: symbol, side, shares, entry price, stop (if any), and — most
   important — the thesis in the user's own words: why this trade, what
   would prove it wrong, and the exit plan.
2. Write `journal/YYYY-MM-DD-SYMBOL.md`:

   ```markdown
   # SYMBOL — buy N shares @ PRICE (YYYY-MM-DD)
   - Stop: ... / Target: ... / Time horizon: ...
   - Source: (scan hit / briefing mover / user idea)
   - Thesis: ...
   - Wrong if: ...
   - Status: open
   ```

3. Keep it under 15 lines. A journal nobody rereads is a diary.

## Reviewing outcomes

1. List `journal/*.md` with `Status: open`; check ages (5+ and 20+
   trading days are the natural checkpoints).
2. Pull reality: `get_pnl_trade_history` (realized) and
   `get_equity_quotes` for still-open names (unrealized vs entry).
3. For each reviewed entry, append an `## Outcome` section: return so
   far or realized result, whether the stop/plan was honored, thesis
   verdict (right / wrong / right-for-wrong-reason), and one lesson in a
   single sentence. Update `Status:` to closed when the position is gone.
4. Across entries, surface patterns bluntly: repeated lesson lines,
   stops moved, theses that were never falsifiable. Three similar
   lessons are a rule candidate for CLAUDE.md — suggest it.

Mask account numbers if they ever appear; prices and symbols are fine.
