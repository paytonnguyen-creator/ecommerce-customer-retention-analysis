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
| **365** | **3** | **90** | **1,106** | **13.7%** | **0.784** | **0.807** | **+0.023** |
| 180 | 3 | 90 | 1,201 | 16.3% | 0.798 | 0.796 | −0.001 |
| 548 | 3 | 90 | 990 | 12.3% | 0.778 | 0.778 | −0.000 |
| 365 | 1 | 90 | 1,106 | 15.3% | 0.752 | 0.757 | +0.005 |
| 365 | 5 | 90 | 1,106 | 12.1% | 0.854 | 0.841 | −0.013 |
| 365 | 3 | 60 | 1,124 | 13.5% | 0.780 | 0.786 | +0.006 |
| 365 | 3 | 120 | 1,087 | 14.0% | 0.792 | 0.798 | +0.006 |

The returner rate stays in a 12–16% band and behavioural AUC in a 0.75–0.85
band across every variant, so neither is an artefact of one arbitrary
threshold. The acoustic delta ranges **−0.013 to +0.023** and straddles zero in
four of the seven. The conclusion is a property of the data, not of the
definitions.

What the sweep does *not* cover are two properties of the LIBRARY, both of
which turned out to matter more than any of these four constants: how
genre-polarised it is (§6) and how long it is (§3).

## 3. Censoring: train on the old, score the new

A track needs `90 + 365 + 180 = 635` days of observation before its label
means anything. Younger tracks are marked **unlabelable** and dropped from
training entirely — **265 of 1,371 here, 19% of the library**.

This is not a technicality, it is the design. Labelling a six-month-old track
"never came back" would be labelling it for being six months old, and a model
trained on that would learn to predict recency. The 265 held-out tracks then
become the deliverable — the modern songs, scored by a model fitted on songs
whose verdict is already in.

### History length is the binding constraint, and it is not a parameter

635 days is a fixed cost per track, so it eats a much larger share of a short
history. Rerunning the identical pipeline on a 13.4-year listener against the
7.6 years a 19-year-old actually has:

| | 13.4 years | 7.6 years |
|---|---|---|
| Labelable tracks | 1,250 | 1,106 |
| Unlabelable (too new) | 124 (9%) | 265 (19%) |
| Returner rate | 19.4% | 13.7% |
| Hold-out interval width | 0.044 | 0.060 |

Two of those move for structural reasons worth separating. The **unlabelable
share doubles** because a fixed 635-day cost is a bigger fraction of a shorter
run. The **returner rate falls** because a return needs somewhere to happen:
with 7.6 years of history there is simply less room after the dormancy window
for a track to come back in, so genuine returners get scored as
non-returners for want of runway. That is right-censoring, and it biases the
base rate down rather than adding noise.

The practical reading: for a young listener this method is running near its
floor. It works, and everything it reports gets a wider interval than the same
account would give in ten years' time.

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
| Memory-evoking songs are more arousing and emotionally intense | Jakubowski & Eerola 2022 | `arousal_index()`, `valence_intensity()` | **Coefficients right-signed; hold-out interval still contains zero** |
| Bounded, distinctive contexts encode better | general memory research | `enc_concentration` | **Rejected** — 53% attenuation under control |

### Why the bump does not rank tracks

The bump weight is a function of age at encoding. Across a long history it
varies from 0.35 to 0.99 and is genuinely informative. Across a 19-year-old's
history it does not vary at all: an account opened at 11 and running to 19 sits
entirely inside the window, so **100% of this library carries a weight above
0.85** and a variable taking one value cannot order anything.

Which is the honest version of a fact that reads as a headline: *your whole
library is in the reminiscence bump* is simultaneously the most striking thing
the psychology says here and the reason it contributes nothing to the ranking.

Folding it into the index anyway would change no ordering while making the
output look more grounded in the literature than it is. It is reported
alongside the score and kept out of it.

### Why `arousal` is not in the joint model

`arousal = 0.6·energy + 0.4·loudness_norm` — a deterministic function of two
predictors already in the block. Fitting all three makes them fight over one
signal and leaves none of the coefficients readable. Arousal is fitted alone
(**+0.19 log-odds per SD**) and reported separately.

`valence_intensity = |valence − 0.5|·2` is a *non-linear* transform of valence,
so that pair is not collinear and both stay in. It sits at **+0.19**, behind
cluster membership at **+0.54**.

## 6. Clustering

K-Means over z-scored acoustic features, `k` chosen by silhouette across 2–8
rather than asserted. It selected **k = 2** (silhouette 0.57) while the demo's
simulator generated **six** worlds — a real limitation on display. On
overlapping acoustic blobs K-Means recovers the dominant axis, not the
taxonomy, and silhouette monotonically prefers the coarser split (0.57 → 0.20
from k=2 to k=8). Six genres in, two clusters out.

Those two clusters *do* separate on the outcome — **14.8% vs 6.3%** return
rate — and cluster membership is the strongest acoustic term in the model at
**+0.54**. That is a change from an earlier run of this project, and the reason
for it is worth stating plainly.

### The library's shape mattered more than any constant

The simulated library was reshaped partway through this work: from a generic
six-genre spread to a **polarised two-pole** one — a rap/trap pole against a UK
house and electronic pole — matching a real stated taste. Nothing about the
model, the label or the four constants changed. The acoustic hold-out delta
moved from **+0.000 to +0.019**. Shortening the history to a 19-year-old's 7.6
years then took it to **+0.023**, with the interval widening to match.

That is the most important sensitivity in the project and it is not in
`sensitivity.csv`, because it is not a parameter. **How much acoustic features
help depends on how genre-polarised the library is.** Two distant scenes give
the acoustic block real variance to exploit; one scene, however deep, does not.

The practical consequence: a single published number for "do audio features
predict musical nostalgia" is reporting a property of whoever's library it was
computed on. This project's number is +0.023, CI [−0.007, +0.053], on a
two-pole library with 7.6 years of history, and it should not be lifted out of
that sentence.

Clusters are named from their own centroids (the two features furthest from the
global mean, with direction) so the labels are derived rather than imposed by
someone who already knows what they want the answer to be.

## 7. Long-form content, and why it outranked the psychology

`enc_completion` is `ms_played / duration_ms` and it is one of the model's
strongest features. That is fine until the library contains 40–90 minute DJ
sets, live mixes and Boiler-Room-style recordings, where the metric stops
meaning anything: twenty minutes of an hour-long set scores **0.28**, the same
as abandoning a three-minute track after fifty seconds.

Because completion is a top-three feature, every mix in the library was being
pushed to the bottom of the shortlist for being long. Not a modelling subtlety
— a format bug with a large, systematic, one-directional effect.

The fix is a judgment, stated rather than tuned: **engagement with long-form is
an absolute amount of time, not a fraction.**

| Change | Value | Effect |
|---|---|---|
| `COMPLETION_REFERENCE_MS` | 8 min | Denominator cap. Past this, staying counts rather than finishing. |
| `LONG_FORM_MS` | 15 min | Threshold for the `is_long_form` indicator. |
| `is_long_form` | model feature | Lets mixes carry their own baseline instead of distorting everyone's. |

`is_long_form` immediately became the **strongest feature in the entire model
at −1.41 log-odds** — ahead of every acoustic feature, ahead of play count,
ahead of skip rate.

Two honest notes on it. First, with a capped denominator nearly every long-form
play saturates at completion 1.0, so the indicator is partly *absorbing* an
inflated completion signal rather than measuring a property of mixes. That is
what it is for, but it means the −0.83 should not be read as "mixes are
forgettable", and the fact that it grew from −0.83 to −1.41 when the history
shortened is consistent with absorption rather than with a stable effect.
Second, the eight-minute cap is arbitrary in exactly the way the
four constants are, and unlike them it is not swept. It should be.

The wider point is uncomfortable and worth keeping: the largest single
improvement in a project about music psychology came from noticing a units
problem in a denominator.

## 8. The playlist's artist cap

`MAX_PER_ARTIST = 2` assumes a broad library. Someone whose listening is
concentrated in a handful of artists cannot fill thirty slots at two apiece,
and the failure mode is silent — a short playlist that looks like the model
found nothing.

So the cap **relaxes** until the list fills, and the applied value is written
to `metrics.json` under `shortlist_selection`. On a seven-artist library the
cap lands at 5 and the note says so. A thirty-track list built at five per
artist is a different object from one built at two, and which one you got
should not be something you reverse-engineer from the output.

## 9. Charts

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

## 10. Hard questions

**Isn't "comes back after a year" just "songs I like"?**
Partly, and the model says so — completion rate and skip rate are its two
strongest features. But 13.7% of tracks return while far more than 13.7% were
liked, so preference is necessary and not sufficient. What the model is really
ranking is *durable* preference, which is the closest observable thing to the
question asked.

**The AUC is 0.78. Isn't that suspiciously good for a hard problem?**
It is good because the problem got easier when it was restated. Predicting
whether someone replays a song is much easier than predicting an emotional
response twenty years out. The AUC is honest about the restated question and
says nothing about the original one.

**On simulated data, doesn't the model just recover the simulator?**
Partly, and that is the only claim made for it. The simulator puts a real but
small acoustic effect in (`+0.35` arousal, `+0.25` valence intensity). The
analysis recovers it in the coefficients and still cannot clear zero in
hold-out AUC — an interval of [−0.002, +0.042] around an effect that is
genuinely there. That is the pipeline being honest rather than powerful: it
declines to report a gain it cannot measure, even when the gain exists.

**Why not gradient boosting?**
It would likely add a couple of points of AUC and remove the ability to say
which feature did what. The deliverable is an argument about why a song is on a
playlist. That trade goes the other way here.

**What would change the conclusion?**
A real account with acoustic features available and ≥ 3,000 labelable tracks.
The hold-out interval here is 0.060 wide around +0.023; roughly four times the
labelable sample would halve it, and an acoustic effect of the size the
literature implies would resolve one way or the other. Until then the claim is
bounded: *not distinguishable from zero at this sample size, on this library
shape and this history length*, not *no effect*. For a 19-year-old, waiting is
also a valid experiment: the same account in five years clears the labelling
threshold for everything currently unlabelable.

## 11. What this cannot know

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
