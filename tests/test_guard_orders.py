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
