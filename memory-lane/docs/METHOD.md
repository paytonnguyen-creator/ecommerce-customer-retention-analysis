# Method notes

Everything here is decisions and their consequences. The findings are in the
[README](../README.md); the numbers are in [metrics.json](../outputs/metrics.json).

---

## 1. The substitution, and what it costs

The brief asked which songs will trigger nostalgia in twenty years. That
question has no ground truth and never will, so it was replaced:

> **A track is a RETURNER if it went dormant for ≥ 365 days and then came back
> for ≥ 3 more plays.**

This is a real behaviour with a real label. It is also **not nostalgia**, and
the gap matters:

| Nostalgia | The returner label |
|---|---|
| A felt state | A pattern of timestamps |
| Can be triggered once and never repeated | Requires repeated behaviour |
| Includes songs you avoid *because* they hurt | Counts those as non-returners |
| Includes music you never streamed | Invisible |

The third row is the sharpest cost. A song welded to something painful may be
one you deliberately never play again — maximum autobiographical weight, scored
zero here. The label systematically misses avoidance, and nothing in the data
can fix that.

What it buys is everything else: a target that can be held out, scored,
bootstrapped and argued with.

## 2. The four constants

| Constant | Value | Why |
|---|---|---|
| `DORMANCY` | 365 days | Long enough that a return is re-engagement rather than a gap in rotation; short enough to leave usable history. |
| `RETURN_PLAYS` | 3 | One play is an algorithmic accident — a radio seed, a shuffled playlist. Three is a choice. |
| `ENCODING_WINDOW` | 90 days | A season. Long enough for a pattern, short enough to precede the outcome by years. |
| `OBSERVE_AFTER` | 180 days | Time for a return to actually happen after the dormancy window closes. |
| `PLAY_FLOOR_MS` | 30,000 | Spotify's own definition of a stream. Borrowed rather than invented. |

All five were chosen, not measured. `sensitivity.py` sweeps the first four and
writes [outputs/sensitivity.csv](../outputs/sensitivity.csv):

| dormancy | return plays | encoding window | labelable | returner rate | AUC behaviour | AUC + acoustics | Δ |
|---|---|---|---|---|---|---|---|
| **365** | **3** | **90** | **1,237** | **17.9%** | **0.785** | **0.786** | **+0.000** |
| 180 | 3 | 90 | 1,288 | 20.1% | 0.806 | 0.810 | +0.004 |
| 548 | 3 | 90 | 1,190 | 16.1% | 0.743 | 0.762 | +0.019 |
| 365 | 1 | 90 | 1,237 | 19.8% | 0.729 | 0.738 | +0.010 |
| 365 | 5 | 90 | 1,237 | 16.7% | 0.819 | 0.813 | −0.007 |
| 365 | 3 | 60 | 1,245 | 17.8% | 0.729 | 0.739 | +0.010 |
| 365 | 3 | 120 | 1,230 | 18.1% | 0.764 | 0.778 | +0.014 |

The returner rate stays in a 16–20% band and behavioural AUC in a 0.73–0.82
band across every variant, so neither is an artefact of one arbitrary
threshold. The acoustic delta ranges **−0.007 to +0.019** and straddles zero.
The conclusion is a property of the data, not of the definitions.

## 3. Censoring: train on the old, score the new

A track needs `90 + 365 + 180 = 635` days of observation before its label
means anything. Younger tracks are marked **unlabelable** and dropped from
training entirely.

This is not a technicality, it is the design. Labelling a six-month-old track
"never came back" would be labelling it for being six months old, and a model
trained on that would learn to predict recency. The 134 held-out tracks then
become the deliverable — the modern songs, scored by a model fitted on songs
whose verdict is already in.

**The known weakness:** train and score sets are separated by time, so any
drift in listening habits sits between them. A model fitted on how the listener
behaved at 15 is being applied to how they behave at 21. `age_at_first_play` is
in the model, which absorbs some of it and none of it cleanly. A proper fix
needs a temporal validation split, and the honest status is that this has not
been done.

## 4. Leakage

Every model feature is measured inside the first 90 days after a track's first
play. Deliberately excluded:

| Excluded | Because |
|---|---|
| `total_plays` | Includes the return itself. |
| `last_play`, lifetime span | Directly encodes whether a return happened. |
| `max_gap_days`, `plays_after_gap` | These *are* the label. |
| Anything after day 90 | Would let the future speak. |

The features that survive: play count and active days in the window, plays
concentrated into its densest fortnight, peak single day, mean completion,
sub-30s skip rate, window span, age at first play, and — where available —
acoustic features, cluster membership, and how old the recording was when first
heard.

## 5. The psychology, mapped to code

Every claim in `psychology.py` is a judgment read off published research, kept
in one file so it can be argued with separately from the estimation.

| Claim | Source | Where it lands | Status |
|---|---|---|---|
| Memory over-represents ages ~10–30, peaking in the late teens | Rubin, Wetzler & Nebes 1986; Rubin & Schulkind 1997 | `encoding_weight()` | Frames which era matters; **excluded from the per-track score** |
| For music the peak sits at ~14–22 | Krumhansl & Zupnick 2013 | curve parameters | Same |
| Memory attaches to songs heard *often*, not songs rated highly | Janata, Tomic & Rubin 2007 | `enc_plays`, `enc_active_days` | **Supported** — behavioural features carry the model |
| Memory-evoking songs are more arousing and emotionally intense | Jakubowski & Eerola 2022 | `arousal_index()`, `valence_intensity()` | **Coefficients right-signed, discrimination nil** |
| Bounded, distinctive contexts encode better | general memory research | `enc_concentration` | **Rejected** — 61% attenuation under control |

### Why the bump does not rank tracks

The bump weight is a function of age at encoding. Across a whole history that
varies from 0.35 to 0.99 and is genuinely informative. Across the tracks being
*scored* — all first played within the last two years, at essentially one age —
it is a constant, and a constant ranks nothing.

Folding it into the index anyway would change no ordering while making the
output look more grounded in the literature than it is. It is reported
alongside the score and kept out of it.

### Why `arousal` is not in the joint model

`arousal = 0.6·energy + 0.4·loudness_norm` — a deterministic function of two
predictors already in the block. Fitting all three makes them fight over one
signal and leaves none of the coefficients readable. Arousal is fitted alone
(**+0.07 log-odds per SD**) and reported separately.

`valence_intensity = |valence − 0.5|·2` is a *non-linear* transform of valence,
so that pair is not collinear and both stay in. It is the strongest acoustic
term at **+0.40**.

## 6. Clustering

K-Means over z-scored acoustic features, `k` chosen by silhouette across 2–8
rather than asserted. It selected **k = 2** (silhouette 0.47) — essentially the
acoustic/electric axis. The demo's simulator generated **six** worlds, so this
is a real limitation on display: on overlapping acoustic blobs, K-Means
recovers the dominant axis and not the taxonomy. Silhouette monotonically
prefers the coarser split (0.47 → 0.27 from k=2 to k=8).

The clusters also fail to separate keepers from forgettables — 19% vs 15%
return rate. The same negative result the AUC comparison gives, from a
different direction.

Clusters are named from their own centroids (the two features furthest from the
global mean, with direction) so the labels are derived rather than imposed by
someone who already knows what they want the answer to be.

## 7. Charts

Five SVGs, regenerated by `run_memory_lane.py`. Fixed `svg.hashsalt` and
`metadata={"Date": None}` strip the sources of run-to-run variation, so
identical inputs produce byte-identical files and a reader can confirm the
figures came from the code rather than from a graphics editor.

Palette is the three-slot categorical set validated in both light and dark
mode. Two constraints shaped the figures:

- **The bump figure is two stacked panels sharing an x-axis, not one panel with
  two y-scales.** Encoding weight and share-of-library are different measures;
  putting them on one axis would invent a relationship between their units.
- **Sonic worlds are small multiples, not a multi-colour scatter.** Categorical
  hues past the third cannot be told apart pairwise under colour-vision
  deficiency at scatter density, so identity is carried by facet position with
  a single highlight hue.

## 8. Hard questions

**Isn't "comes back after a year" just "songs I like"?**
Partly, and the model says so — completion rate and skip rate are its two
strongest features. But 17.9% of tracks return while far more than 17.9% were
liked, so preference is necessary and not sufficient. What the model is really
ranking is *durable* preference, which is the closest observable thing to the
question asked.

**The AUC is 0.79. Isn't that suspiciously good for a hard problem?**
It is good because the problem got easier when it was restated. Predicting
whether someone replays a song is much easier than predicting an emotional
response twenty years out. The AUC is honest about the restated question and
says nothing about the original one.

**On simulated data, doesn't the model just recover the simulator?**
Partly, and that is the only claim made for it. The simulator put a real
acoustic effect in (`+0.35` arousal, `+0.25` valence intensity) and the
analysis **failed to detect it in hold-out AUC** while recovering it in the
coefficients. That is a demonstration of the pipeline's honesty rather than its
power: it did not report a gain it could not measure.

**Why not gradient boosting?**
It would likely add a couple of points of AUC and remove the ability to say
which feature did what. The deliverable is an argument about why a song is on a
playlist. That trade goes the other way here.

**What would change the conclusion?**
A real account with acoustic features available and ≥ 3,000 labelable tracks.
The hold-out interval here is 0.058 wide; roughly four times the labelable
sample would halve it, and an acoustic effect of the size the literature
implies would become visible if it is there. Until then the claim is bounded:
*no detectable effect at this sample size*, not *no effect*.

## 9. What this cannot know

- **Social context.** Who you heard it with is a first-order driver of musical
  nostalgia and leaves no trace in a listening log.
- **Lyrical self-relevance.** `speechiness` detects spoken words, not whether
  the words meant anything. No proxy is used.
- **Life events.** The bump is about developmental period; a move, a breakup or
  a loss binds music at any age.
- **Off-platform listening.** Radio, live shows, someone else's aux cable, and
  everything before the account existed.

These are in `psychology.BLIND_SPOTS` and copied into every `metrics.json`, so
the limits travel with the numbers instead of living only in a document nobody
opens.
