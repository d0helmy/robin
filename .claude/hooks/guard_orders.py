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
    except (KeyError, InvalidOperation):
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
    try:
        allowed, reason = evaluate(payload)
    except Exception:
        print("ORDER BLOCKED by guard hook: unexpected payload shape; "
              "denying (fail closed).", file=sys.stderr)
        return 2
    if not allowed:
        print(f"ORDER BLOCKED by guard hook: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
