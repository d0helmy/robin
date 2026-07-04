#!/usr/bin/env python3
"""PreToolUse guard for Robinhood order tools.

Denies any order that is not a stocks-only, plain-limit order at or under
the per-order cap, and enforces a daily notional circuit breaker via a
local ledger of approved orders. Fails closed: unparseable input, an
unreadable ledger, or a breached daily cap all deny.
"""
import json
import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

MAX_ORDER_USD = Decimal("500")
DAILY_CAP_USD = Decimal("1500")
LEDGER_RETENTION_DAYS = 30
EQUITY_TOOL = "mcp__robinhood-trading__place_equity_order"
OPTION_TOOL = "mcp__robinhood-trading__place_option_order"


def evaluate(payload):
    """Return (allowed, reason). Reason is empty when allowed.

    May raise on malformed payload shapes; the CLI wrapper denies on any
    exception.
    """
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
    except (KeyError, InvalidOperation):
        return False, "Order must include numeric quantity and limit_price."
    if quantity <= 0 or limit_price <= 0:
        return False, "quantity and limit_price must be positive."

    notional = quantity * limit_price
    if notional > MAX_ORDER_USD:
        return False, (f"Order notional ${notional} exceeds the "
                       f"${MAX_ORDER_USD} per-order cap.")
    return True, ""


def check_daily_cap(notional, entries, today):
    """Return (allowed, reason) for the daily notional circuit breaker.

    entries is the ledger list; only entries whose date equals today count.
    Malformed entries deny (fail closed).
    """
    total = Decimal("0")
    try:
        for entry in entries:
            if entry.get("date") == today:
                total += Decimal(str(entry["notional"]))
    except (InvalidOperation, KeyError, TypeError, AttributeError):
        return False, ("order ledger has malformed entries; denying "
                       "(fail closed). Inspect the ledger file.")
    if total + notional > DAILY_CAP_USD:
        return False, (f"Order notional ${notional} would take today's "
                       f"approved total to ${total + notional}, over the "
                       f"${DAILY_CAP_USD} daily cap "
                       f"(${total} already approved today).")
    return True, ""


def _ledger_path():
    return os.environ.get("GUARD_LEDGER_PATH") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "order_ledger.json")


def _today_et():
    as_of = os.environ.get("GUARD_AS_OF")
    if as_of:
        return as_of
    return datetime.now(ZoneInfo("America/New_York")).date().isoformat()


def _load_ledger(path):
    """Return (entries, ok). Missing file is an empty ledger; anything
    unreadable or non-list returns ok=False so the caller fails closed."""
    try:
        with open(path) as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return [], True
    except Exception:
        return [], False
    if not isinstance(data, list):
        return [], False
    return data, True


def _record_approval(path, entries, today, notional):
    cutoff = (date.fromisoformat(today)
              - timedelta(days=LEDGER_RETENTION_DAYS)).isoformat()
    kept = [e for e in entries if str(e.get("date", "")) >= cutoff]
    kept.append({"date": today, "notional": str(notional)})
    tmp = f"{path}.tmp"
    with open(tmp, "w") as fh:
        json.dump(kept, fh, indent=1)
    os.replace(tmp, path)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        print("Guard could not parse hook payload; denying (fail closed).",
              file=sys.stderr)
        return 2
    try:
        allowed, reason = evaluate(payload)
        if allowed:
            path = _ledger_path()
            today = _today_et()
            entries, ok = _load_ledger(path)
            if not ok:
                allowed, reason = False, (
                    "order ledger is unreadable; denying (fail closed). "
                    "Inspect the ledger file.")
            else:
                order = payload["tool_input"]
                notional = (Decimal(str(order["quantity"]))
                            * Decimal(str(order["limit_price"])))
                allowed, reason = check_daily_cap(notional, entries, today)
                if allowed:
                    _record_approval(path, entries, today, notional)
    except Exception as exc:
        print(f"ORDER BLOCKED by guard hook: unexpected payload shape "
              f"({type(exc).__name__}); denying (fail closed).",
              file=sys.stderr)
        return 2
    if not allowed:
        print(f"ORDER BLOCKED by guard hook: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
