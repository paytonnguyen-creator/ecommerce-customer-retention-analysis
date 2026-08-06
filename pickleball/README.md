# The Pickleball Bottleneck

**[Behavioural audit →](docs/BEHAVIORAL_AUDIT.md)** · **[PRD →](docs/PRD.md)** · **[Walkthrough →](docs/WALKTHROUGH.md)**

Predicting open-play court congestion, and working out what — if anything —
telling players about it in advance is actually worth.

**The question:** open play rations a scarce court by making people queue. What
does that queue cost, who pays it, and can a two-hour-ahead forecast move any of
it?

**The answer, in short:** the forecast is worth a lot to a player and almost
nothing to a parks department. Routing one player to the best slot within ±2
hours cuts their expected wait 43% and halves the chance they go home without a
game. The same behaviour adopted by 15% of peak arrivals moves system-wide wait
by **3.2%** — information redistributes a queue, it does not shrink it. Mean-
while the cheapest lever nobody is pulling is a rotation rule that costs nothing
and delivers three quarters of what a 25% court expansion delivers.

## Findings

| | |
|---|---|
| Share of peak court time spent waiting, not playing | **36%** |
| Peak arrivals who give up because it is busy | **7.7%** |
| Arrivals in the last hour of light who never get a game | **38.8%** |
| Wait following the model's advice vs just turning up | **4.1 min** vs 7.3 |
| Chance of no game: turn up → model → + daylight guardrail | **17.5% → 8.9% → 5.0%** |
| Irreducible forecast error, even knowing true demand | **2.18 min** |
| System-wide peak wait saved by 15% of players shifting | **3.2%** |
| Peak wait saved by changing the rotation rule, at zero cost | **1.9 min** (75% of a 25% court expansion) |

Two results reframed the project. **Waiting is U-shaped** — 11.1 minutes when
the court is nearly empty against 1.8 at the sweet spot, because you need four
people to start a game — which means an app that steers you to the quietest
court is wrong at one end of its own range. And **congestion hides itself**:
from the sweet spot to the busiest hours demand rises 6× and the wait 9×, but
the share who go home without playing rises **52×**. The queue does not get
longer, it sheds people, so queue length is the wrong thing to measure.

## What is real here and what is not

This is the part to read before trusting any number.

| Layer | Status | Source |
|---|---|---|
| Daily weather, 2012–2015 | **Real** | NOAA Seattle, 1,461 days, via `vega_datasets` |
| Hourly temperature shape | **Real** | Same station, 2010 hourly file, used as a by-month diurnal shape |
| Sunrise / sunset / playable hours | **Computed** | NOAA solar algorithm at 47.61°N — 13.9 playable hours in June, 8.0 in December |
| How many people want to play | **Assumed** | `analysis/simulate_courts.py` → `ASSUMPTIONS`, dumped to `data/assumptions.json` |
| Waits, abandonment, policy effects | **Emergent** | Discrete-event simulation of the paddle stack |

The seam matters. A regression fitted to simulated arrivals can only recover the
assumptions that generated them, so every figure that does this is labelled
**RECOVERED** and is treated as a receipt for the pipeline rather than as
evidence. The results that carry the argument are labelled **EMERGENT**: they
follow from eight courts, four players a game, a first-in-first-out paddle rack
and finite patience, and none of them were written down anywhere.

None of the load-bearing findings were inputs — not the U-shape, not the
52× abandonment ratio, not the rotation-rule result, not the daylight cliff.

**Why simulate at all?** No parks department publishes paddle-stack telemetry,
which is precisely why the product in the PRD has a market. Live weather APIs
are blocked by this environment's egress policy, so the weather was taken from
data that ships inside a Python package instead — real observations, real
station, real dates.

## The counterfactuals

Every policy scenario re-draws arrivals, game lengths and patience thresholds
from a stream seeded on `(park, date)` **only** — never on the scenario. The
same people, wanting the same games, on the same afternoon, meet a different
court policy. Differences between scenarios are the policy, not sampling noise.

| Policy | Peak wait | vs today | Effort |
|---|---|---|---|
| Winners stay on | 11.9 min | +1.9 | None — it is a sign on the fence |
| **Today: 8 courts, all four off** | **10.0 min** | — | — |
| App shifts 15% off peak | 9.7 min | −0.3 | Medium — build an app, earn adoption |
| Build 2 more courts (+25%) | 7.5 min | −2.6 | High — capital budget, 12–18 months |

Implementation cost is a judgement, not a computation. Nothing in a court log
says what a programme costs, so effort is recorded per lever and a reader can
disagree with the estimate instead of with the arithmetic.

## Running it

```bash
pip install -r pickleball/analysis/requirements.txt
python pickleball/analysis/prepare_weather.py    # -> data/hourly_weather.csv
python pickleball/analysis/simulate_courts.py    # -> data/park_hours.csv, scenarios.csv   (~2.5 min)
python pickleball/analysis/run_analysis.py       # -> outputs/metrics.json, outputs/figures/*.svg
```

The three large intermediates (`hourly_weather.csv`, `park_hours.csv`,
`scenarios.csv` — about 27 MB) are **not committed**; the three commands above
regenerate them. Everything a reader needs without running anything —
`metrics.json`, the figures, the declared assumptions, the wait histogram — is
in the repo.

Deterministic — same inputs, same numbers. Seeds are SHA-256 of
`(salt, park, date)` rather than Python's `hash()`, which is salted per process
and would silently break reproducibility across runs. Figures use a fixed
`svg.hashsalt` and carry no embedded timestamp, so identical inputs give
byte-identical SVGs.

Every number quoted in this README, in the PRD, in the behavioural audit and in
the walkthrough is read from `outputs/metrics.json`, which `run_analysis.py`
produces.

## Layout

```
analysis/prepare_weather.py   real NOAA weather + solar geometry -> hourly grid
analysis/simulate_courts.py   declared arrival model + paddle-stack queue simulation
analysis/run_analysis.py      cost -> bottleneck curve -> forecast -> advice -> policies
data/assumptions.json         every behavioural assumption, in the open
data/weather_provenance.json  what the weather build produced, for checking
data/wait_histogram.csv       time-to-first-game, binned, by hour
data/hourly_weather.csv       the real weather backbone          (generated)
data/park_hours.csv           one row per park-hour, baseline    (generated)
data/scenarios.csv            per-park-hour under each policy    (generated)
outputs/metrics.json          every number the write-ups quote
outputs/figures/              SVG charts, RECOVERED and EMERGENT labelled
docs/BEHAVIORAL_AUDIT.md      the psychology, tied to named simulator parameters
docs/PRD.md                   the DinkRadar Court Density Score proposal
docs/WALKTHROUGH.md           the argument in presentation order, and the hard questions
```

## Method notes

- **No leakage.** The forecast trains on 2012–2014 and is scored on 2015, a
  materially busier year. Every feature is knowable two hours ahead: calendar,
  park, and a weather forecast. The true arrival intensity is used *only* by
  the oracle, whose job is to measure the noise floor.
- **The oracle is the point.** Handed the true demand, it still posts MAE 2.18
  minutes. That residual is queueing randomness, it is irreducible, and it is
  why the product displays four states instead of a number.
- **The shipped model is not the most accurate one.** Selection rule, fixed in
  advance: lowest absolute bias among models within 1.25× of the best MAE. The
  boosted tree scores 15% better on MAE but runs 0.77 min low, because trees
  cannot extrapolate a growth trend past their training range. Under-promising
  a wait costs more trust than symmetric noise.
- **Abandonment is split by cause.** A first pass reported 17% of peak arrivals
  never getting a game and attributed it to congestion. Most of it was people
  arriving before dark. Congestion-only is 7.7%. The split changes the
  recommendation.
- **The bottleneck curve excludes the last 90 minutes of daylight,** which mix
  a different failure into the same axis.
- **Arrivals are indifferent to crowding.** No social-proof feedback, on
  purpose — it makes the demand-shifting result an optimistic bound rather than
  a favourable one.
- **The private/public distinction is load-bearing.** Every advice number
  assumes the player is marginal: one person moving does not change the queue.
  True at low adoption, false at high adoption, and the failure mode gets worse
  exactly as the product succeeds.
