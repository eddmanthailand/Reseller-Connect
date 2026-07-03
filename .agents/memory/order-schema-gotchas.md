---
name: Order schema gotchas
description: Non-obvious cross-table facts when querying orders (tracking, shipping)
---

# Order schema gotchas

- The `orders` table has **no `tracking_number` column**. Tracking numbers live on
  `order_shipments.tracking_number` (an order can split into multiple shipments).
  To show tracking for an order, subquery/join `order_shipments`
  (e.g. earliest non-null: `ORDER BY id LIMIT 1`).
  **Why:** selecting `tracking_number` directly off `orders` throws
  `UndefinedColumn` and 500s the endpoint — bit the guest tracking lookup.

- Shipping fee weight-bracket matching convention: **match-or-zero**, never fall
  back to the heaviest bracket. Mirror `/api/calculate-shipping` (settings.py):
  `min_weight <= w AND (max_weight IS NULL OR max_weight >= w) ORDER BY min_weight DESC LIMIT 1`,
  charge 0 if no row matches.
  **Why:** a heaviest-bracket fallback silently overcharges when weight ranges have
  gaps or start above 0g.
