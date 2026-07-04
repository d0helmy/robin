# Robinhood Trading Skills & Guard Hook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Four trading skills (`/portfolio`, `/brief`, `/trade`, `/scan`) for the connected `robinhood-trading` MCP server, with a PreToolUse hook that mechanically enforces stocks-only, limit-only, ≤$500-per-order rules.

**Architecture:** Project skills in `.claude/skills/` drive the workflows at the prompt level; a Python PreToolUse hook in `.claude/hooks/` provides fail-closed hard enforcement on the two order-placing MCP tools; `CLAUDE.md` carries the standing rules into every session.

**Tech Stack:** Claude Code project skills (SKILL.md), Claude Code hooks (settings.json PreToolUse), Python 3 stdlib only (json, decimal, unittest — no pip installs).

## Global Constraints

- Per-order cap: notional (quantity × limit_price) ≤ **$500.00** exactly (500.00 is allowed, 500.01 is not).
- Order type: only `type == "limit"` may pass the guard. `market`, `stop_market`, `stop_limit` are denied.
- `place_option_order` is denied unconditionally (stocks only).
- Guard fails closed: unparseable or unexpected input → deny (exit 2).
- Live tool schema (verified 2026-07-04): `place_equity_order` requires `account_number`, `symbol`, `side`, `type`; optional `quantity` (string), `limit_price` (string), `dollar_amount` (string, market-only), `stop_price`, `time_in_force` ('gfd'|'gtc'), `market_hours`, `ref_id` (UUID idempotency key).
- Hook contract (Claude Code): stdin receives JSON `{"tool_name": ..., "tool_input": {...}, ...}`; exit 0 = allow, exit 2 = block with stderr shown to the model.
- All money math uses `decimal.Decimal`, never float.
- No new dependencies; `python3` from PATH.
- Commit after every task.

---

### Task 1: Guard hook script (TDD)

**Files:**
- Create: `.claude/hooks/guard_orders.py`
- Test: `tests/test_guard_orders.py`

**Interfaces:**
- Produces: `evaluate(payload: dict) -> tuple[bool, str]` (imported by the test), and a CLI entrypoint reading hook JSON on stdin, exiting 0 (allow) or 2 (deny, reason on stderr). Task 2 registers this script; its path must be exactly `.claude/hooks/guard_orders.py`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_guard_orders.py`:

```python
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / ".claude" / "hooks" / "guard_orders.py"
sys.path.insert(0, str(HOOK.parent))

from guard_orders import evaluate  # noqa: E402

EQUITY = "mcp__robinhood-trading__place_equity_order"
OPTION = "mcp__robinhood-trading__place_option_order"


def equity_order(**overrides):
    order = {
        "account_number": "123456",
        "symbol": "AAPL",
        "side": "buy",
        "type": "limit",
        "quantity": "2",
        "limit_price": "100.00",
    }
    order.update(overrides)
    order = {k: v for k, v in order.items() if v is not None}
    return {"tool_name": EQUITY, "tool_input": order}


class TestEvaluate(unittest.TestCase):
    def test_valid_limit_under_cap_allowed(self):
        allowed, reason = evaluate(equity_order())
        self.assertTrue(allowed, reason)

    def test_exactly_at_cap_allowed(self):
        allowed, reason = evaluate(
            equity_order(quantity="5", limit_price="100.00"))
        self.assertTrue(allowed, reason)

    def test_one_cent_over_cap_denied(self):
        allowed, reason = evaluate(
            equity_order(quantity="1", limit_price="500.01"))
        self.assertFalse(allowed)
        self.assertIn("cap", reason)

    def test_market_order_denied(self):
        allowed, reason = evaluate(
            equity_order(type="market", limit_price=None))
        self.assertFalse(allowed)
        self.assertIn("limit", reason)

    def test_stop_limit_denied(self):
        allowed, _ = evaluate(
            equity_order(type="stop_limit", stop_price="95.00"))
        self.assertFalse(allowed)

    def test_option_order_denied(self):
        allowed, reason = evaluate(
            {"tool_name": OPTION, "tool_input": {"quantity": "1"}})
        self.assertFalse(allowed)
        self.assertIn("stocks only", reason)

    def test_unknown_tool_denied(self):
        allowed, _ = evaluate(
            {"tool_name": "something_else", "tool_input": {}})
        self.assertFalse(allowed)

    def test_dollar_amount_denied(self):
        allowed, _ = evaluate(equity_order(dollar_amount="100.00"))
        self.assertFalse(allowed)

    def test_stop_price_on_limit_denied(self):
        allowed, _ = evaluate(equity_order(stop_price="95.00"))
        self.assertFalse(allowed)

    def test_missing_quantity_denied(self):
        allowed, _ = evaluate(equity_order(quantity=None))
        self.assertFalse(allowed)

    def test_missing_limit_price_denied(self):
        allowed, _ = evaluate(equity_order(limit_price=None))
        self.assertFalse(allowed)

    def test_non_numeric_quantity_denied(self):
        allowed, _ = evaluate(equity_order(quantity="abc"))
        self.assertFalse(allowed)

    def test_zero_quantity_denied(self):
        allowed, _ = evaluate(equity_order(quantity="0"))
        self.assertFalse(allowed)

    def test_negative_price_denied(self):
        allowed, _ = evaluate(equity_order(limit_price="-1"))
        self.assertFalse(allowed)


class TestCli(unittest.TestCase):
    def run_hook(self, stdin_text):
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=stdin_text, capture_output=True, text=True)

    def test_valid_order_exits_zero(self):
        import json
        proc = self.run_hook(json.dumps(equity_order()))
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_market_order_exits_two_with_reason(self):
        import json
        proc = self.run_hook(json.dumps(
            equity_order(type="market", limit_price=None)))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("BLOCKED", proc.stderr)

    def test_malformed_json_exits_two(self):
        proc = self.run_hook("this is not json")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("fail closed", proc.stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/dia/Documents/robinh && python3 -m unittest tests.test_guard_orders -v 2>&1 | head -5`
Expected: FAIL with `ModuleNotFoundError: No module named 'guard_orders'`

- [ ] **Step 3: Write the implementation**

Create `.claude/hooks/guard_orders.py`:

```python
#!/usr/bin/env python3
"""PreToolUse guard for Robinhood order tools.

Denies any order that is not a stocks-only, plain-limit order at or under
the per-order cap. Fails closed: unparseable input is denied.
"""
import json
import sys
from decimal import Decimal, InvalidOperation

MAX_ORDER_USD = Decimal("500")
EQUITY_TOOL = "mcp__robinhood-trading__place_equity_order"
OPTION_TOOL = "mcp__robinhood-trading__place_option_order"


def evaluate(payload):
    """Return (allowed, reason). Reason is empty when allowed."""
    tool = payload.get("tool_name", "")
    if tool == OPTION_TOOL:
        return False, "Options orders are not allowed (stocks only)."
    if tool != EQUITY_TOOL:
        return False, f"Unexpected tool {tool!r}; this guard denies by default."

    order = payload.get("tool_input") or {}
    if order.get("type") != "limit":
        return False, (f"Order type {order.get('type')!r} rejected: "
                       "only plain limit orders are allowed.")
    if "dollar_amount" in order:
        return False, ("dollar_amount is not allowed; "
                       "use quantity + limit_price.")
    if "stop_price" in order:
        return False, "stop_price is not allowed on a plain limit order."

    try:
        quantity = Decimal(str(order["quantity"]))
        limit_price = Decimal(str(order["limit_price"]))
    except (KeyError, InvalidOperation, ArithmeticError):
        return False, "Order must include numeric quantity and limit_price."
    if quantity <= 0 or limit_price <= 0:
        return False, "quantity and limit_price must be positive."

    notional = quantity * limit_price
    if notional > MAX_ORDER_USD:
        return False, (f"Order notional ${notional} exceeds the "
                       f"${MAX_ORDER_USD} per-order cap.")
    return True, ""


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        print("Guard could not parse hook payload; denying (fail closed).",
              file=sys.stderr)
        return 2
    allowed, reason = evaluate(payload)
    if not allowed:
        print(f"ORDER BLOCKED by guard hook: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/dia/Documents/robinh && python3 -m unittest tests.test_guard_orders -v`
Expected: all 17 tests PASS (`OK`)

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/guard_orders.py tests/test_guard_orders.py
git commit -m "feat: add fail-closed guard hook for Robinhood order tools"
```

---

### Task 2: Register the hook in project settings

**Files:**
- Create: `.claude/settings.json`

**Interfaces:**
- Consumes: `.claude/hooks/guard_orders.py` from Task 1.
- Produces: PreToolUse registration active for every future session in this project (requires session restart to load).

- [ ] **Step 1: Write the settings file**

Create `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "mcp__robinhood-trading__place_equity_order|mcp__robinhood-trading__place_option_order",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/guard_orders.py\""
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Verify the registered command works exactly as configured**

Run (simulates how Claude Code invokes it, including the env var):

```bash
cd /Users/dia/Documents/robinh && \
CLAUDE_PROJECT_DIR="$PWD" sh -c 'echo "{\"tool_name\":\"mcp__robinhood-trading__place_option_order\",\"tool_input\":{}}" | python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/guard_orders.py"'; echo "exit=$?"
```

Expected: stderr `ORDER BLOCKED by guard hook: Options orders are not allowed (stocks only).` and `exit=2`

- [ ] **Step 3: Validate JSON syntax**

Run: `python3 -m json.tool .claude/settings.json > /dev/null && echo VALID`
Expected: `VALID`

- [ ] **Step 4: Commit**

```bash
git add .claude/settings.json
git commit -m "feat: register PreToolUse guard for order-placing tools"
```

---

### Task 3: CLAUDE.md standing rules

**Files:**
- Create: `CLAUDE.md`

**Interfaces:**
- Produces: standing rules loaded into every session; `/trade` (Task 4) references the same rules — wording of cap/limit/confirm must match exactly.

- [ ] **Step 1: Write CLAUDE.md**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add standing trading rules to CLAUDE.md"
```

---

### Task 4: /trade skill

**Files:**
- Create: `.claude/skills/trade/SKILL.md`

**Interfaces:**
- Consumes: rules wording from Task 3; guard behavior from Task 1.
- Produces: `/trade` pipeline other skills point users to (Task 7 `/scan` links here).

- [ ] **Step 1: Write the skill**

Create `.claude/skills/trade/SKILL.md`:

```markdown
---
name: trade
description: Prepare, confirm, and place a stock order on Robinhood, or check/cancel existing orders. Use when the user wants to buy or sell a stock, place an order, check order status, or cancel an order.
---

# Trade — confirmed stock order pipeline

Real money. Follow every step in order; no step may be skipped or merged.

## Placing an order

1. **Account.** Use the account number the user already confirmed this
   session. Otherwise call `get_accounts`, list accounts with
   `agentic_allowed=true`, and ask which to use. Never silently default.
2. **Quote & tradability.** `get_equity_quotes` and `get_equity_tradability`
   for the symbol. If not tradable or halted, stop and report.
3. **Context.** `get_equity_positions` (current stake) and `get_portfolio`
   (buying power). Report both to the user.
4. **Construct a plain limit order.** `type=limit`, whole-share `quantity`
   (fractional shares don't work with limit orders), explicit `limit_price`
   (for immediate fills suggest a marketable limit near ask for buys / near
   bid for sells), `time_in_force` gfd unless the user asks for gtc.
   Notional (quantity × limit_price) must be ≤ $500 — if the user's request
   exceeds it, say so and ask them to resize; do not resize yourself.
5. **Robinhood pre-flight.** `review_equity_order` with the full order.
   Surface every alert it returns.
6. **Read-back.** Present exactly: symbol, side, shares, limit price,
   estimated cost, time in force, account, current position, buying-power
   impact, and any review alerts. Then ask the user to reply `confirm`.
7. **Confirmation gate.** Only the exact word `confirm` proceeds. Anything
   else aborts (report aborted, no order placed). A confirmation covers one
   order only.
8. **Place.** Generate one UUID as `ref_id` (`python3 -c "import uuid; print(uuid.uuid4())"`),
   then `place_equity_order` with identical parameters plus that `ref_id`.
9. **Verify.** `get_equity_orders` for the order state; report filled /
   pending / rejected with details. If the place call failed ambiguously
   (timeout/5xx), check `get_equity_orders` FIRST; if absent, retry once
   with the SAME `ref_id`.

If the guard hook blocks the order, relay its reason verbatim and wait for
the user — never work around the guard.

## Checking orders

`get_equity_orders` filtered to what the user asked; summarize state,
fill price, remaining quantity.

## Cancelling an order

Identify the order via `get_equity_orders`, show it, get a yes/no
confirmation, then `cancel_equity_order` and re-check state to confirm
cancellation.
```

- [ ] **Step 2: Verify frontmatter parses**

Run: `python3 -c "import pathlib; t = pathlib.Path('.claude/skills/trade/SKILL.md').read_text(); assert t.startswith('---') and t.count('---') >= 2 and 'name: trade' in t; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/trade/SKILL.md
git commit -m "feat: add /trade confirmed order pipeline skill"
```

---

### Task 5: /portfolio skill

**Files:**
- Create: `.claude/skills/portfolio/SKILL.md`

**Interfaces:**
- Consumes: account-selection rule from CLAUDE.md (Task 3).
- Produces: `/portfolio` review; `/brief` (Task 6) reuses its held-tickers framing but shares no files.

- [ ] **Step 1: Write the skill**

Create `.claude/skills/portfolio/SKILL.md`:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/portfolio/SKILL.md
git commit -m "feat: add /portfolio review skill"
```

---

### Task 6: /brief skill

**Files:**
- Create: `.claude/skills/brief/SKILL.md`

**Interfaces:**
- Consumes: account-selection rule from CLAUDE.md (Task 3).
- Produces: `/brief` pre-market rundown.

- [ ] **Step 1: Write the skill**

Create `.claude/skills/brief/SKILL.md`:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/brief/SKILL.md
git commit -m "feat: add /brief market briefing skill"
```

---

### Task 7: /scan skill

**Files:**
- Create: `.claude/skills/scan/SKILL.md`

**Interfaces:**
- Consumes: `/trade` handoff (Task 4).
- Produces: `/scan` screening workflow.

- [ ] **Step 1: Write the skill**

Create `.claude/skills/scan/SKILL.md`:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/scan/SKILL.md
git commit -m "feat: add /scan screening skill"
```

---

### Task 8: Live verification (manual, requires session restart)

**Files:** none created — this task validates the whole install.

**Interfaces:**
- Consumes: everything from Tasks 1–7.

- [ ] **Step 1: Full test suite green**

Run: `cd /Users/dia/Documents/robinh && python3 -m unittest discover -s tests -v`
Expected: all tests PASS

- [ ] **Step 2: Restart the session**

User exits and runs `claude --continue` so the new hook and skills load.
Skills and hooks are loaded at session start; nothing built here is active
until restart.

- [ ] **Step 3: Read-only skills live**

Run `/portfolio`, `/brief`, and `/scan` once each; confirm each produces
its output using only read-only tools.

- [ ] **Step 4: Guard fires in-session**

With the user's consent, dry-run the guard: attempt a deliberately
over-cap order (e.g. 2 shares × $300 limit) through `place_equity_order`.
Expected: the hook blocks it with `ORDER BLOCKED ... exceeds the $500
per-order cap` and no order reaches Robinhood. This is safe by design —
the block happens before the tool executes.

- [ ] **Step 5: /trade dry run to the review step**

Run `/trade` on a cheap liquid ticker, stop after the read-back (user
replies anything other than `confirm`). Expected: pipeline aborts cleanly,
`get_equity_orders` shows no new order.

- [ ] **Step 6: Optional live order**

Only if the user wants: one small user-confirmed limit order well under
the cap, verified filled or pending via `get_equity_orders`.
