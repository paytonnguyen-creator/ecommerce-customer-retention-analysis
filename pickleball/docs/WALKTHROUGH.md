# Walkthrough — the argument in presentation order

*How to present this in ten minutes, and the questions that should be asked.*

---

## The ten-minute version

**1. The hook (30 seconds).**
The worst part of pickleball is not losing. It is standing at the paddle rack
for half an hour on a Tuesday evening, having driven twenty minutes to get
there. I wanted to know whether telling people the line was long before they
left the house would actually fix that.

**2. The honesty problem, stated first (1 minute).**
No parks department publishes paddle-stack telemetry, so the sessions here are
simulated. That creates a trap: if I write down "demand peaks at 70°F" and then
run a regression that discovers demand peaks at 70°F, I have discovered
nothing. So the project is built in two layers, and the seam is enforced in the
code:

- The **weather is real** — four years of Seattle NOAA observations, with
  hourly temperature reconstructed from the same station's diurnal shape, and
  sunrise/sunset computed from solar geometry.
- The **arrival model is a declared assumption**, written in one dictionary,
  dumped to JSON, and labelled `RECOVERED` on every figure it touches.
- The **queue is a mechanism**, not an assumption. Eight courts, four to a
  game, first-in-first-out paddles, finite patience. What comes out of that is
  labelled `EMERGENT`, and only `EMERGENT` results are allowed to reach a
  recommendation.

*Show:* `temperature_response.svg` — and say plainly that this chart is a
receipt for the pipeline, not a finding.

**3. The first real finding: the wait is U-shaped (2 minutes).**
I expected the wait to rise with demand. It does — but it also rises when the
court is nearly empty, to a mean of 11.1 minutes against 1.8 at the sweet spot.
The reason is obvious in hindsight and invisible in the assumptions: you need
four people to start a game. On an empty court you are not queueing for a
court, you are queueing for opponents.

This immediately kills the naive version of the product. An app that sends you
to the quietest court is giving bad advice at one end of its own range.

*Show:* `bottleneck_curve.svg`.

**4. The second real finding: congestion hides itself (2 minutes).**
From the sweet spot to the busiest hours, demand rises 6×, the wait rises 9× —
but the share of people who go home without a game rises **52×**. The queue is
self-limiting: it does not get longer, it sheds people. Anyone who measures
congestion by looking at how many paddles are in the rack is measuring the
survivors.

That reframes the metric. This project reports *abandonment*, not queue length.

**5. The third finding, which I did not go looking for (1.5 minutes).**
Splitting abandonment by cause: 7.7% of peak arrivals give up because it is
busy. **38.8%** of arrivals in the last hour of usable light go home without
playing — and 9.2% of all arrivals land in that hour. Outdoor courts in Seattle
run 13.9 playable hours in June and 8.0 in December. The single largest source
of wasted trips is not congestion at all. It is the sun going down, and it is
computable a year in advance with no model whatsoever.

*Show:* `daylight_cliff.svg`.

**6. The model, and its ceiling (2 minutes).**
Train on 2012–2014, score on 2015 — a genuinely harder year, because demand
grows. Four candidate models plus an **oracle** that is handed the true demand
that generated the arrivals. The oracle cannot be beaten by any amount of
feature engineering, and it still posts a mean absolute error of 2.18 minutes.
That is the queue's own randomness, and it is the number that decides the
interface: **you can never honestly display "12 minutes."** The product ships
four states instead.

I shipped the model with the *second*-best accuracy on purpose. The boosted
tree scores MAE 2.54 but runs 0.77 minutes low, because trees cannot
extrapolate a growth trend past the edge of their training data. Detrending
first costs accuracy (3.09) and buys calibration (bias 0.13). For a product
that makes a promise about your evening, being systematically optimistic is a
worse failure than being noisy.

*Show:* `forecast_accuracy.svg`.

**7. What the advice is worth, and to whom (1.5 minutes).**
To a player: the best slot within ±2 hours cuts the expected wait from 7.3 to
4.1 minutes and drops the chance of not playing at all from 17.5% to 8.9% —
and to **5.0%** once you refuse to recommend slots without 90 minutes of light.
The guardrail beats the model.

To a parks department: 15% of peak arrivals shifting moves system-wide wait by
**3.2%**. Information redistributes the queue; it does not shrink it. So this is
a consumer product, not a municipal one, and the PRD says so.

*Show:* `advice_value.svg`.

**8. The recommendation I did not want to make (1 minute).**
The cheapest lever is not the app. Switching open play from "winners stay on" to
"all four off" is worth 1.9 minutes of mean peak wait and 5.8 points of
abandonment. Building two more courts — a 25% capacity increase — is worth 2.6
minutes. **The free rule change delivers 75% of what the capital project
delivers.** If I were advising the parks department rather than building the
app, that is the entire recommendation, and it fits on a laminated sign.

*Show:* `policy_comparison.svg`.

---

## The hard questions

**"You simulated the data. Why should I believe any of this?"**
You should not believe the arrival model — it is mine, and it is in
`assumptions.json` for you to attack. You should believe the queueing results,
because they follow from mechanics rather than from my inputs, and none of them
were inputs. I did not write down that waiting would be U-shaped, that
abandonment would outrun wait 8-to-1, that a rule change would rival a capital
project, or that darkness would beat congestion. Those fell out. The three
findings the recommendation rests on are all of that kind.

**"Isn't the temperature finding circular?"**
Completely, and it is labelled that way on the figure. It is a pipeline test.
The blueprint for this project asked me to "prove demand spikes at 65–75°F" —
you cannot prove that against data you generated. What you can do is say so.

**"Why not use a real dataset?"**
I tried. The weather API this project wanted is blocked by the environment's
egress policy, and no public dataset of paddle-stack occupancy exists — which
is itself the reason the product has a market. What I could get real, I got
real: NOAA observations for the exogenous drivers and solar geometry for the
daylight constraint. The daylight finding is the payoff for that decision, and
it would not exist if I had invented the calendar.

**"Your abandonment numbers looked wrong at first. What happened?"**
They were wrong. My first pass reported 17% of peak arrivals never getting a
game and called it congestion. Splitting by time-of-day showed 40% of that was
people arriving an hour before dark. The congestion-only figure is 7.7%. The
error mattered — it would have justified building courts to solve a problem
that a sunset table solves.

**"Why is the mean wait only ten minutes? That's not a bottleneck."**
Because patience truncates it. Median patience before a first game is set at 28
minutes, so the queue cannot grow deeper than people will tolerate — it converts
excess demand into departures instead. If you think real players wait longer,
raise `patience_first_game_median_min` and re-run: waits go up, abandonment
comes down, and the qualitative conclusions do not move, because they are about
ratios between scenarios that all share the same parameter.

**"You picked the model with worse accuracy."**
Yes, by a stated rule, chosen before looking at which model it selected: lowest
absolute bias among models within 1.25× of the best MAE. Both models' full
scores are in `metrics.json`, so you can overrule me. My argument is that
telling someone the wait is 10 minutes when it is 18 costs more than telling
them 15 when it is 10.

**"What would you build first?"**
The daylight guardrail, and I would ship it without the model. It is a lookup
table, it needs no training data, and it moves the metric that matters more than
the forecast does. Everything else is v2.

**"What's the biggest weakness?"**
Herding. Every number here assumes the player taking the advice is marginal —
one person moving does not change the queue. That is true at low adoption and
false at high adoption, and the product gets worse exactly as it succeeds. The
15%-adoption scenario is the only place I test it, and 15% is a guess.
