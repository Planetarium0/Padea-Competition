# 17 — GST handling is an open question

**Severity:** Medium (affects financial accuracy).
**Files:** `plans/gst.md` (one-line question), `scripts/actions/register_orders.py`
(uses raw `Price per Item`), `data/schema.py`
(stores `Price Includes GST` checkbox).

`plans/gst.md` is one line:

> Should migrations automatically convert to with gst?

The current state:

- `Caterers.Price Includes GST` is stored, populated by the menu
  migration, never read by any other code.
- `register_orders.py` computes `total_cost = total_meals × price_per_item
  + delivery_total` using the raw stored price.
- Across caterers the field is a mix of true and false (depending on
  how they quote).
- So the "Total Cost" on a Weekly Order is not GST-normalised — two
  caterers' totals aren't directly comparable.

This will silently mismatch when the coordinator reconciles totals
against invoices.

### Fix

Decide one of:

- **Normalise on import**: in `migrations/caterer_menus.py`, if
  `Price Includes GST` is false, multiply by 1.10 and store the
  inclusive price. The field then becomes informational.
- **Normalise on use**: keep raw prices, but have `register_orders.py`
  compute inclusive totals using the flag.
- **Display both**: show pre-GST and post-GST in the email body.
