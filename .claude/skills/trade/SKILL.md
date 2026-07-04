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
   **Daily-loss halt:** for buys, also check `get_realized_pnl` with
   span=day. If today's realized loss exceeds 2% of account value, stop —
   report the halt instead of preparing the order. Resume only if the user
   explicitly says to override the loss halt (that override lasts for one
   order only).
4. **Construct a plain limit order.** `type=limit`, whole-share `quantity`
   (fractional shares don't work with limit orders), explicit `limit_price`
   (for immediate fills suggest a marketable limit near ask for buys / near
   bid for sells), `time_in_force` gfd unless the user asks for gtc.
   Notional (quantity × limit_price) must be ≤ 500 USD — if the user's request
   exceeds it, say so and ask them to resize; do not resize yourself.
   **Risk-based sizing:** when the user gives (or asks for) a stop price,
   suggest shares = floor((account value × 1%) ÷ (entry − stop)), then
   apply the notional and buying-power limits. Present it as a suggestion
   with the math shown; the user picks the final size. Never invent a stop
   to force a size.
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
the user — never work around the guard. Besides the per-order cap, the
hook enforces a 1,500 USD daily total across all approved orders (resets
each trading day, US Eastern).

After a fill is verified, offer to record the trade with `/journal`.

## Checking orders

`get_equity_orders` filtered to what the user asked; summarize state,
fill price, remaining quantity.

## Cancelling an order

Identify the order via `get_equity_orders`, show it, get a yes/no
confirmation, then `cancel_equity_order` and re-check state to confirm
cancellation.
