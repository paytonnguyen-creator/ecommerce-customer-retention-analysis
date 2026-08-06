# PRD — DinkRadar: the Court Density Score

**Owner:** Payton Nguyen · **Status:** Proposal · **Evidence:** 843,581 simulated player-visits across 5 parks × 8 courts, driven by four years of real Seattle NOAA weather (2012–2015)

> **Read this first.** The court sessions behind these numbers are simulated;
> the weather and the daylight are real. Anything below that depends on *how
> many people want to play* is an assumption I wrote down in
> `analysis/simulate_courts.py`. Anything that depends on *what happens to them
> once they arrive* is emergent, and those are the findings this document is
> built on. The distinction is enforced in the code and labelled on every
> figure.

---

## 1. Problem

Open play rations a scarce court by making people stand in line, and the line
is expensive. Across the peak block (17:00–19:59), **36% of the time a player
spends at the park is spent waiting rather than playing.** In the busiest year
modelled, the mean wait for a first game is **10.0 minutes**, and the
distribution has a long right tail.

But the wait is not the injury. The injury is the people who go home without
playing at all, and there are two distinct populations doing it:

| Cause | Rate | Why it matters |
|---|---|---|
| **Congestion** — too many paddles, gave up | **7.7%** of peak arrivals | Routable: there is usually a better slot two hours either side |
| **Darkness** — arrived in the last hour of usable light | **38.8%** of those arrivals | Not routable, and **9.2% of all arrivals** land in this bucket |

The second row is the one nobody is managing. It is five times worse than
congestion and it is caused by a fact no park publishes: an unlit outdoor court
in Seattle offers 13.9 playable hours in June and **8.0 in December**.

## 2. The decision this informs

**Is a demand-forecasting product worth building — and if so, who is the
customer?**

There are two plausible buyers and they want opposite things. A parks
department wants aggregate wait across the system to fall. A player wants
*their own* evening to go well. The analysis says these are not the same
problem, and that assuming they are is how this product gets built for the
wrong person.

## 3. What the analysis found

| Finding | Evidence | Implication |
|---|---|---|
| Advice has a large **private** return | Best slot within ±2h cuts expected wait **7.3 → 4.1 min** (−43%), capturing 69% of what perfect hindsight offers | Worth building — for the player |
| Advice has a negligible **public** return | 15% of peak arrivals shifting to the quietest nearby slot moves system-wide peak wait by **0.3 min (−3.2%)** | Do not sell this to a parks department as congestion relief |
| The forecast has a hard floor | An oracle handed the *true* demand still posts **MAE 2.18 min**; the shipped model posts 3.09 | **Never display a number.** No model can honour a "12 minute" promise |
| The daylight guardrail beats the wait model | Never-played: 17.5% → 8.9% with the model → **5.0%** by refusing slots under 90 min of light | The cheapest feature is the most valuable one |
| Waiting is **U-shaped** | 11.1 min wait when nearly empty vs 1.8 min at ~13 arrivals/hr | Recommending the *quietest* slot is wrong advice; recommend the *best* one |
| The parks department's best lever is free, and it is not this app | Switching rotation from "winners stay" to "all four off" is worth **1.9 min**, or **75% of the benefit of building two more courts** | Say so out loud |

## 4. Proposal

Ship **DinkRadar**, a consumer app whose core object is a **Court Density
Score**: a two-hour-ahead prediction of what a player will actually experience
at a given court, expressed as a state, never as a number.

**In scope**

- **Four states, not minutes.** `DEAD` / `GOOD` / `BUSY` / `PACKED`, derived
  from predicted arrivals per hour against the U-curve. `DEAD` is a warning,
  not an invitation — it is the "nobody to play with" arm.
- **The daylight guardrail, shipped in v1.** Never surface a slot with under 90
  minutes of usable light. This needs no model at all — it is solar geometry
  and a lookup — and it does more for the metric that matters than the
  forecast does.
- **"Best slot in the next 3 hours"** as the primary call to action, ranked by
  predicted state and filtered by the guardrail.
- **A stated confidence band**, because the noise floor is real and permanent.

**Out of scope**

- **A predicted wait in minutes.** The oracle's floor of 2.18 minutes means a
  displayed "12 min" is wrong by ±2 even with perfect demand knowledge. A
  number invites a promise the physics cannot keep.
- **Selling congestion relief to municipalities.** The 3.2% system-level effect
  does not support that pitch, and pitching it anyway is how this becomes a
  product nobody renews.
- **Live court-side sensors** in v1. The point is to inform the decision made
  *before leaving the house*; a sensor tells you what you could already see by
  driving there.

## 5. Size of the prize

| Lever | Population | Assumption | Value |
|---|---|---|---|
| Route to the best nearby slot | Peak-hour players who can flex ±2h | Model captures 69% of available saving | **3.15 min saved per visit** |
| Daylight guardrail | The 9.2% of arrivals landing in the last hour of light | Guardrail obeyed | **Never-played 17.5% → 5.0%** |

The second lever is roughly a **twelve-point reduction in wasted trips** and it
costs one `if` statement against a sunrise/sunset table. It should ship first
and it should ship alone if it has to.

## 6. Success metrics

**Primary:** share of app-influenced visits that end in at least one game.
Target ≥ 92%, against the 82.5% baseline for players who simply turn up when
they meant to.

**Secondary:** mean wait to first game on app-influenced visits.

**Ship / kill:** if the never-played rate on influenced visits does not beat the
unassisted baseline by ≥ 5pp in one season, kill it. The wait-time saving alone
does not justify the build.

**Guardrails**
- *Prediction calibration.* Mean bias must stay within ±0.5 min. The shipped
  model was selected on this and not on accuracy — a boosted tree with a
  15% better MAE was rejected for running **0.77 min low**, because a product
  that systematically under-promises the wait burns trust faster than a noisier
  one that is centred.
- *Herding.* If enough users take the same recommendation, the recommendation
  destroys itself. Monitor the variance of arrivals across recommended slots;
  the 15%-adoption scenario suggests this is not a near-term risk, but it is
  the failure mode that gets worse exactly as the product succeeds.

**Counter-metric:** share of recommendations landing in `DEAD` hours. Optimising
for "shortest wait" will walk people into empty courts, which the U-curve says
is its own failure.

## 7. What I would tell the parks department instead

Not to buy this. Their cheapest available lever is a laminated sign: standardise
open play on **all four off** rather than winners-stay. It is worth 1.9 minutes
of mean peak wait and 5.8 points of abandonment, it costs nothing, and it
delivers three quarters of what a 25% court expansion would buy. An app that
moves system-wide wait by 3.2% is not competitive with that, and a proposal that
does not say so is selling rather than analysing.
