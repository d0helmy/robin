import json
import os
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / ".claude" / "hooks" / "guard_orders.py"
sys.path.insert(0, str(HOOK.parent))

from guard_orders import check_daily_cap, evaluate  # noqa: E402

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


class TestDailyCap(unittest.TestCase):
    def entry(self, date, notional):
        return {"date": date, "notional": notional}

    def test_empty_ledger_allows(self):
        allowed, reason = check_daily_cap(
            Decimal("500"), [], "2026-07-06")
        self.assertTrue(allowed, reason)

    def test_exactly_at_daily_cap_allowed(self):
        ledger = [self.entry("2026-07-06", "500.00"),
                  self.entry("2026-07-06", "500.00")]
        allowed, reason = check_daily_cap(
            Decimal("500"), ledger, "2026-07-06")
        self.assertTrue(allowed, reason)

    def test_over_daily_cap_denied(self):
        ledger = [self.entry("2026-07-06", "500.00"),
                  self.entry("2026-07-06", "500.00"),
                  self.entry("2026-07-06", "500.00")]
        allowed, reason = check_daily_cap(
            Decimal("100"), ledger, "2026-07-06")
        self.assertFalse(allowed)
        self.assertIn("daily", reason)

    def test_prior_day_entries_ignored(self):
        ledger = [self.entry("2026-07-05", "500.00"),
                  self.entry("2026-07-05", "500.00"),
                  self.entry("2026-07-05", "500.00")]
        allowed, reason = check_daily_cap(
            Decimal("500"), ledger, "2026-07-06")
        self.assertTrue(allowed, reason)

    def test_malformed_ledger_entry_fails_closed(self):
        ledger = [{"date": "2026-07-06", "notional": "garbage"}]
        allowed, reason = check_daily_cap(
            Decimal("500"), ledger, "2026-07-06")
        self.assertFalse(allowed)


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.ledger = Path(self.tmpdir.name) / "order_ledger.json"

    def run_hook(self, stdin_text, as_of="2026-07-06"):
        env = dict(os.environ,
                   GUARD_LEDGER_PATH=str(self.ledger),
                   GUARD_AS_OF=as_of)
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=stdin_text, capture_output=True, text=True, env=env)

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

    def test_null_payload_exits_two(self):
        proc = self.run_hook("null")
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertTrue(
            "BLOCKED" in proc.stderr or "fail closed" in proc.stderr,
            proc.stderr)

    def test_list_payload_exits_two(self):
        proc = self.run_hook("[]")
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertTrue(
            "BLOCKED" in proc.stderr or "fail closed" in proc.stderr,
            proc.stderr)

    def test_non_dict_tool_input_exits_two(self):
        import json
        proc = self.run_hook(json.dumps(
            {"tool_name": EQUITY, "tool_input": "not-a-dict"}))
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertTrue(
            "BLOCKED" in proc.stderr or "fail closed" in proc.stderr,
            proc.stderr)

    def test_nan_quantity_exits_two(self):
        import json
        proc = self.run_hook(json.dumps(
            equity_order(quantity="NaN", type="limit", limit_price="100.00")))
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("BLOCKED", proc.stderr)

    def test_approved_order_recorded_in_ledger(self):
        proc = self.run_hook(json.dumps(equity_order()))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        entries = json.loads(self.ledger.read_text())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["date"], "2026-07-06")
        self.assertEqual(Decimal(entries[0]["notional"]), Decimal("200.00"))

    def test_denied_order_not_recorded(self):
        proc = self.run_hook(json.dumps(
            equity_order(type="market", limit_price=None)))
        self.assertEqual(proc.returncode, 2)
        self.assertFalse(self.ledger.exists())

    def test_fourth_max_order_hits_daily_cap(self):
        order = json.dumps(equity_order(quantity="5", limit_price="100.00"))
        for i in range(3):
            proc = self.run_hook(order)
            self.assertEqual(proc.returncode, 0,
                             f"order {i + 1}: {proc.stderr}")
        proc = self.run_hook(order)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("BLOCKED", proc.stderr)
        self.assertIn("daily", proc.stderr)

    def test_daily_cap_resets_next_day(self):
        order = json.dumps(equity_order(quantity="5", limit_price="100.00"))
        for _ in range(3):
            self.assertEqual(self.run_hook(order).returncode, 0)
        self.assertEqual(self.run_hook(order).returncode, 2)
        proc = self.run_hook(order, as_of="2026-07-07")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_corrupt_ledger_fails_closed(self):
        self.ledger.write_text("this is not json")
        proc = self.run_hook(json.dumps(equity_order()))
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertTrue(
            "BLOCKED" in proc.stderr or "fail closed" in proc.stderr,
            proc.stderr)


if __name__ == "__main__":
    unittest.main()
