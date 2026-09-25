# Pricing rules and calibration

All seed rates are demonstrations, not supplier quotations, copied competitor rates or proven profit figures. The original $1,400 storefront agreement is preserved as a draft price override; the software cannot establish its actual profit without actual costs.

## Calculation model

Inputs are rectangular finished dimensions in inches and whole-number quantities. A contour shape is estimated by its bounding rectangle. Calculations use Decimal; persisted money uses integer cents.

```text
single_piece_sqft = width_inches * height_inches / 144
net_sqft = single_piece_sqft * quantity
material_sqft = net_sqft * (1 + waste_percent / 100)
labor_hours = labor_minutes_per_unit * quantity / 60

raw_estimated_cost = material_sqft * material_cost_per_sqft
                   + setup_cost
                   + labor_hours * shop_labor_cost_per_hour
estimated_cost = raw_estimated_cost * (1 + overhead_percent / 100)

rate_price = setup_price
           + single_piece_sqft * weighted_quantity * sell_per_sqft
           + labor_hours * shop_labor_sell_per_hour
margin_floor = estimated_cost / (1 - target_margin_percent / 100)
line_price = max(rate_price, product_minimum, margin_floor)
```

The margin floor is rounded up to a cent. Ordinary money rounding is half-up. Waste is a cost allowance, not extra finished square footage charged as though delivered to the customer. Labor allowances increase linearly with quantity and are not quantity-discounted. Do not include installation labor in a bundled cost/rate and add the same labor again.

### Quantity bands

Bands are **graduated**, not all-units discounts. For bands beginning at 1 with multiplier 1.0, 100 with 0.9, and 500 with 0.8, the first 99 pieces use 1.0, pieces 100-499 use 0.9, and pieces 500 onward use 0.8. This avoids a sudden lower total when adding one item at a tier boundary. Minimum charges and the cost floor can override the band calculation.

This is this application's transparent model, not a claim to reproduce Sticker Mule's proprietary calculation. Separate products can represent materials, finishing methods or packaging configurations. The calculator does not currently choose roll core sizes, nesting patterns or vehicle models.

### Job-level adjustments

Owner **Final charges** supports extra services selling price, extra estimated cost, agreed pretax merchandise/services price, shipping/delivery selling charge, tax dollar amount and deposit percentage. An override replaces the calculated product/services pretax price; tax and shipping are added afterward. Enter an explanation for overrides or extra costs.

For custom quotes, tax is entered manually as an amount, not calculated by jurisdiction. Online checkout uses the separately configured pickup rate or shipping tax flow described in CHECKOUT.md. The deposit percentage applies to the full quoted total including entered tax and shipping. A $1,400 agreement described as tax-inclusive must be reconciled into its correct components before publishing; the seed does not assume how the agreement treats tax.

Additional costs should include supplier freight, removal, equipment, sheet purchases and other costs not captured in product rates. The displayed contribution subtracts estimated costs plus the configured buffer, not audited actual expenses. It is not a guarantee of net profit. Recorded employee time does not automatically change a saved quote or payroll.

## Guardrails

- Calculations and pricing fingerprints are checked on the server. A browser cannot choose an arbitrary checkout price.
- Every new job saves the applicable rates and cost-setting snapshots. Catalog changes do not silently reprice existing jobs.
- The example public warning remains until the owner enables reviewed public rates.
- Oversize dimensions and review-only products return budget estimates requiring shop review.
- Custom quote requests remain drafts until staff review. Eligible standard orders can be accepted and purchased immediately after checkout is configured; the server freezes the price and fulfillment policy.
- Custom-job financial revisions revoke acceptance and the old payment link. Online checkout orders cannot be repriced or given manual duplicate receipts; use a separately reviewed changed-scope job and an explicit payment/refund plan.

## Calibrate before launch

For each product, test at least a small, standard and large order against your actual completed jobs. Include material purchase yield, setup, finishing, equipment and labor. Check each quantity boundary and the minimum charge.

For acrylic, a 25.42-square-foot finished sign can require purchasing more than 25.42 square feet. The generic waste percentage does not solve full-sheet availability, thickness, freight or cut-yield constraints. Use an actual supplier quote and a job cost adjustment.

### ACM sign thickness, September 2026

The single-sided ACM signs product defaults to 3 mm at $14/sq ft and offers 6 mm at $20/sq ft. The 6 mm selection adds $3.50/sq ft to the estimated material cost. Both use the existing $20 setup, $65 product minimum, and optional $2/sq ft laminate. Installation and artwork design are separate. For a single sign with no laminate, 24 × 36 inches calculates to $104 (3 mm) or $140 (6 mm); 48 × 96 inches calculates to $468 or $660. Gloss laminate adds $12 or $64 respectively to those 6 mm examples.

The $3.50/sq ft incremental cost covers the higher of two published 4 × 8 sheet comparisons before freight: Curbell lists 3 mm at $64.64 and 6 mm at $111.96; Blue Ridge lists 3 mm at $64.32 and 6 mm at $172.67. This benchmark is not a supplier commitment for Tampa pickup or delivered cost. Verify actual sheet purchase, yield and freight for unusually large or multi-panel jobs.

- `https://www.curbellplastics.com/product-category/material/aluminum-composite-material-acm/c-tek-panels/`
- `https://blueridgesignsupply.com/products/acm-poly-metal-panel-4x-8-x-3mm`
- `https://blueridgesignsupply.com/products/acm-4-x-8-x-6mm-poly-metal-panel`

For installed wraps, film cost alone is not installed selling price. Confirm coverage, film/laminate, panel plan, removal, vehicle condition, disassembly and installation labor. Both installed wraps and print-only wrap panels are quote-only. Their costs/workflows remain distinct; wholesale print rates are not installed retail pricing.

Reference UX researched September 17, 2026:

- Sticker Mule bulk stickers: size, quantity, unit price, artwork and proof flow. `https://www.stickermule.com/uses/bulk-stickers`
- WePrintWraps: wholesale print quoting, distinct from a shop's installed-wrap price. `https://quote.weprintwraps.com/horizontal-quote`

No competitor rate table, branding, product imagery or third-party source code is included.


## Purchase eligibility in v0.2

An administrator sets instant purchase, requires-installation, wrap classification, dimensions and quantity limits for each product. Server checks prevent wraps or installed items from using standard checkout even if an instant-purchase flag is selected. Review-only and oversized products stay on the quote path. Example standard products are stickers, labels, magnets, banners, ACM signs and yard signs; confirm their material/finish specifications and applicable shipping before enabling them. Current seeded storefront perf and acrylic-face replacement include custom/installation scope and remain quote-only. Add separate supply-only products for straightforward pickup work with appropriate rates and limits.

One public online order has one product, one size and one design with a chosen quantity. Supported products can offer material and finish choices. Per-order coupons and automatic carrier charges are not implemented. The merchandise estimate is visible before checkout and configured tax/shipping is reviewed before payment.
