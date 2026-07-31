# PRD — Second-Purchase Program

**Owner:** Payton Nguyen · **Status:** Proposal · **Data:** CDNOW transaction log (23,570 customers, Q1 1997 cohort, followed to June 1998)

---

## 1. Problem

**62.5% of customers never place a second order.** They are acquired once, they buy once, and the relationship ends. Revenue is correspondingly top-heavy: the top 20% of customers generate 67.8% of all revenue, and the top 5% generate 36.7%.

That concentration is usually read as "we have great whales." The more useful reading is the inverse: the business is spending acquisition budget on a majority of customers who return nothing beyond their first basket, and no amount of optimising the top of the file changes that.

## 2. The decision this informs

Where should the next unit of retention effort go — **building a model that predicts who will return, or building a treatment applied to everyone?**

Those are very different programs. One is a data science investment that pays off in targeting efficiency. The other is a lifecycle marketing investment that pays off in coverage. Choosing wrong wastes a quarter.

## 3. What the analysis found

| Finding | Evidence | Implication |
|---|---|---|
| First-order data barely predicts who returns | Hold-out **AUC 0.576** against a 0.375 base rate | A targeting model is not worth building |
| When customers do return, they return fast | Median **57 days**; ~60% of second purchases fall inside 90 days | There is a narrow, well-defined window to act in |
| Basket **value** predicts repeat; item **count** does not | Title count attenuates from +0.22 to +0.04 (≈82%) once value is controlled | Merchandise toward value, not toward add-ons |
| Acquisition month barely matters | Cohort coefficients within ~0.06 log-odds | Not a lever worth pulling |

The first and second findings together are the argument. Because the model cannot tell you *who* to treat, and because the window in which treatment could work is short and known, the correct build is **a timed intervention applied to every first-time buyer** — not a scoring pipeline.

## 4. Proposal

Ship a **second-purchase program**: a sequence timed to the 30–90 day window after a first order, sent to every first-time buyer, with content weighted toward higher-value titles rather than cheap add-ons.

**In scope**
- Trigger on first order; sequence lands day 30, day 55, day 80
- Recommendations weighted to basket value, not item count
- A holdout arm, permanently

**Out of scope**
- Any propensity/targeting model. The AUC says it would not earn its keep.
- Discount-led reactivation. Nothing here tests price sensitivity, so a discount would be an untested guess with a permanent margin cost.

## 5. Size of the prize

| Lever | Population | Assumption | Value |
|---|---|---|---|
| Timed second-purchase nudge | 14,743 one-and-done customers | +3.0pp conversion | **≈ $39.7k** incremental 180-day repeat revenue |
| Lift bottom-quartile first baskets | 6,364 customers | 12.9pp gap, 25% captured | **≈ $18.4k** |

Both figures are deliberately conservative. The 3pp lift is *assumed, not measured* — it is the number the holdout exists to prove or kill. The 25% capture rate reflects that the benchmark group differs from the target group in ways beyond the lever itself.

## 6. Success metrics

**Primary:** 180-day repeat rate among first-time buyers, treatment vs. holdout.

**Ship / kill:** ≥ 2pp lift at p < 0.05 after one full 180-day cohort. Below 1pp, kill it — the program is not free and a sub-1pp effect will not clear its own cost.

**Guardrails:** revenue per recipient (must not fall — a lift bought by discounting is not a win), unsubscribe rate, margin per repeat order.

**Counter-metric:** average basket value of the second order. If the program lifts repeat rate by driving cheap purchases, it is moving the metric without moving the business.

## 7. Risks

| Risk | Mitigation |
|---|---|
| The 3pp lift is invented | It is flagged as an assumption, and the holdout is non-negotiable |
| Findings are correlational, not causal | Only levers surviving statistical control are proposed; the item-count lever was rejected for exactly this reason |
| Data is from 1997 | Timing and concentration patterns are structural; the specific channel tactics are not transferable and are not proposed |

## 8. What would change my mind

If the holdout shows < 1pp after a full cohort, the window hypothesis is wrong and the constraint is more likely product selection than timing. The next investigation would be first-basket composition, not lifecycle timing.
