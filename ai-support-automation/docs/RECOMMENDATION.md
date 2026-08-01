# Recommendation memo

**To:** Steering committee, customer operations
**Re:** AI assistant for tier-1 contact handling — go / no-go and operating design
**Basis:** Analysis of 23,700 customer requests (CLINC150 benchmark); all figures per 100,000 contacts

---

## Recommendation

**Proceed, with abstention built in from day one — not deferred to a later phase.**

The program is worth **$359,891 per 100,000 contacts** at the recommended operating point: 72.6% of contacts handled with no human, 95.1% of those correct.

Three amendments to the proposal as it stands:

1. **The business case must be restated.** Its $588k assumes every contact is automatable. Requests the system does not support cannot be automated at any model quality, so the physical ceiling is $478,909. The current case overstates the achievable maximum by 23%.
2. **Reallocate the first tranche of spend from model quality to routing.** The abstention rule is worth $211,418. A flawless classifier — an unreachable ideal, not a realistic upgrade — would be worth $49,636.
3. **Measure the out-of-scope rate in our own queue before we commit to a number.** It is the assumption the case is most sensitive to and among the cheapest to measure.

---

## What we are actually buying

| Policy | Coverage | Accuracy on what it handled | Value per 100k |
|---|---|---|---|
| All human (today) | — | — | baseline |
| Automate everything | 100% | 75.6% | $148,473 |
| **Automate above 0.53 confidence** | **72.6%** | **95.1%** | **$359,891** |
| Perfect model + perfect abstention | 81.8% | 100% | $478,909 |
| Business case as submitted | 100% | 100% | $588,000 — not achievable |

The gap between rows 2 and 3 is a routing rule. Same model, same traffic.

---

## Stage gates

Each gate has a number attached and a defined action if the number is missed. A gate that cannot fail is not a gate.

| Gate | Test | Proceed if | If missed |
|---|---|---|---|
| **0 — Baseline** | Sample 500 live contacts; label in-scope vs out-of-scope; measure true cost per contact | Out-of-scope rate below 25% | Above 25%, re-run the case before building — value falls roughly linearly and the payback assumptions no longer hold |
| **1 — Shadow** | Router scores live traffic, answers nothing, for 2 weeks | Abstention-adjusted accuracy within 5pp of benchmark on our own traffic | Retune the threshold on our data; do not proceed on benchmark numbers |
| **2 — Limited live** | Two lowest-error domains only, abstention on, human review of every auto-resolved contact | Error rate on auto-handled contacts below 2% | Raise the threshold, re-measure; do not widen scope |
| **3 — Widen** | Add domains in ascending order of measured error rate, per-domain thresholds | Each domain independently clears gate 2 | Hold that domain at human-handled; the others still proceed |
| **4 — Steady state** | Continuous sampling of auto-resolved contacts | Silent-failure rate stable or falling | Freeze coverage, investigate drift |

Gate 0 is not a formality. It is the cheapest way to discover the program is worth materially less than proposed, and it happens before the build.

---

## Risk register

| Risk | Why it bites | Leading indicator | Mitigation |
|---|---|---|---|
| **Silent failure on unsupported requests** | 9.3% of out-of-scope requests are answered confidently. No ticket is reopened, no alert fires, the customer just leaves. Deflection dashboards will look excellent throughout | Rising auto-resolution rate with flat or falling CSAT | Continuous sampling of auto-resolved contacts by a human; treat sampled error rate, not deflection rate, as the health metric |
| **Pooled calibration monitoring misleads** | The router is under-confident on supported traffic and unknown traffic errs the other way. Pooled, they cancel: calibration error is 0.098 on supported traffic and *improves* to 0.050 on the live queue. Rising unknown traffic reads as an improving model | Calibration error falling while sampled error rate is flat or rising | Track the signed calibration gap for supported and unsupported traffic separately. Never report the pooled figure |
| **Deflection rate becomes the target** | It is the easiest metric to move and moving it destroys value — lowering the threshold raises deflection and lowers net value | Anyone proposing a coverage target | Report deflection and sampled error rate together, never separately. Target net value, not coverage |
| **Cost-of-error assumption is too low** | At $18.08 per bad answer, full automation destroys value. Our $12 is a judgment | Complaint handling cost per re-contact | The thresholded policy stays positive across every tested assumption — this is the reason to keep the dial rather than automate everything |
| **Intent drift** | Supported intents decay as products change; today's in-scope becomes tomorrow's out-of-scope | Confidence distribution shifting downward over time | Monitor the monthly confidence distribution, not just accuracy; re-tune thresholds quarterly |
| **Benchmark ≠ our queue** | 92.4% is on short, single-intent, crowdsourced English. Real tickets are longer and messier | Gate 1 shadow accuracy | Gate 1 exists solely to catch this before any customer is exposed |
| **Vendor incentive misalignment** | Vendors are measured on deflection and demo accuracy, both of which point away from abstention | Contract terms tied to coverage | Tie commercial terms to sampled error rate and net value, not to deflection |

---

## What would change this recommendation

Stated in advance, so the answer is not retrofitted:

- **Out-of-scope rate above ~35% in our queue.** Value falls to about $260k and the program needs re-scoping around a narrower set of intents rather than broader automation.
- **Cost per wrong answer materially above $18.08.** Full automation is already value-destroying at that point; by $30 the optimal threshold has risen to 0.70 and coverage falls far enough that the build may not clear its own cost.
- **No abstention path in the product.** If the assistant cannot hand off mid-conversation, the entire $211k advantage disappears and the decision reverts to the $148k full-automation case — which is a much weaker business case and highly exposed to the error-cost assumption.
- **Shadow-mode accuracy more than 5pp below benchmark.** Benchmark transfer is the largest untested assumption in this analysis.

---

## What this analysis does not settle

- It is built on a **public benchmark, not our data.** The economics of the threshold generalise; the specific accuracy does not. Gate 1 is designed to test exactly this.
- **Cost inputs are judgments**, held explicitly and swept, not measured from our systems. Gate 0 replaces them with real numbers.
- It models **single-turn routing**, not multi-turn conversation, escalation mid-conversation, or adversarial use.
- It assumes **a wrong answer costs the same everywhere.** In practice a wrong billing answer and a wrong store-hours answer are not comparable, which likely argues for even more per-domain differentiation than recommended here.
