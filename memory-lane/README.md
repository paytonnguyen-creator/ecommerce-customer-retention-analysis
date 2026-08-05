# Memory Lane — which songs will still hurt in 2046?

**[Method notes →](docs/METHOD.md)** · **[Metrics →](outputs/metrics.json)** · **[Shortlist →](outputs/core_memory_tracks.csv)**

A Spotify listening history, the reminiscence-bump literature, and one question:
among the songs I am playing *now*, which ones will still be pulling on me in
twenty years?

**The problem with that question:** it has no ground truth. Nobody holds a
labelled dataset of songs that turned out to be core memories, so a supervised
model for it would be astrology with a train/test split. The project's first
move is to replace it with a question the data can answer.

**The replacement:** *which songs do I come back to after I have stopped
listening to them?* A track is a **returner** if it went dormant for a year or
more and then came back for at least three more plays. That is not nostalgia —
it is the behavioural shadow nostalgia casts in a listening log, and unlike
nostalgia it can be held out and scored.

**The answer, in short:** behaviour in a song's first ninety days predicts
return at **AUC 0.760**; every acoustic feature Spotify exposes adds **+0.012
[95% CI −0.019, +0.042]** on top — a gain whose interval still contains zero.
And the single largest modelling win in the project came from neither music
psychology nor machine learning. It came from noticing that **hour-long DJ sets
break the completion metric**, which is worth more than every acoustic feature
combined.

## Findings

| | |
|---|---|
| Tracks that came back after a year of silence | **16.9%** |
| Median dormancy before a return | **852 days** (2.3 years) |
| Hold-out AUC, first-90-days behaviour | **0.760** |
| Hold-out AUC, behaviour + acoustics | **0.772** (Δ +0.012, CI [−0.019, +0.042]) |
| Second strongest feature in the model | **`is_long_form`**, −1.00 log-odds |
| Library first played inside the bump window (ages 10–28) | **96.6%** |
| Tracks too new to be labelled at all | **176 of 1,380** (12.8%) |

**The reminiscence bump is a claim about eras, not tracks.** It says music
encoded between roughly 10 and 28 binds hardest. This account opened at **age
8.7**, so **96.6% of the library sits inside that window** and the remaining
3.4% is listening that happened *before the bump properly starts* — the only
part of the history the literature expects to bind weakly.

That near-constancy is exactly why the bump weight ranks nothing. A variable
that is 0.85+ for 24 tracks out of 25 cannot order them. It is deliberately
excluded from the per-track score rather than folded in to make the model look
more scientific.

The corollary is the more interesting half: at 19 the bump is **not finished**.
Roughly a third of the window is still ahead, so this is a measurement taken
mid-event, not after it.

**The most tempting behavioural lever was rejected.** Cramming a song into a
single fortnight looks like a strong negative signal — the top concentration
decile returns at 1.7% against 16.9% overall. But concentration correlates
−0.59 with play count, and the coefficient falls from **−0.57 to −0.17** once
volume is held constant: a **70% attenuation**. Songs crammed into one fortnight
mostly aren't bound to a moment, they were played four times.

## The thing that mattered most was not the psychology

`enc_completion` — what fraction of a track you play — is one of the model's
strongest features. It is computed as `ms_played / duration_ms`, which is
fine until half the library is 40–90 minute DJ sets and live mixes. Twenty
minutes of an hour-long set scores **0.28**, indistinguishable from bailing on
a three-minute track after fifty seconds. Since completion is a top-three
feature, every mix in the library was being quietly pushed to the bottom of the
shortlist for the crime of being long.

The fix is one line of judgment: **engagement with long-form content is an
absolute amount of time, not a fraction.** The denominator is capped at eight
minutes, so past that point staying is what counts rather than finishing, and a
`is_long_form` indicator lets the model give mixes their own baseline.

That indicator became the **second strongest feature in the model at −1.00
log-odds** — ahead of every acoustic feature, ahead of play count and
completion, behind only skip rate. A format problem outranked the entire CogSci
hypothesis. That is the most useful thing this project found, and it is not a
finding about memory at all.

## What the acoustic result actually means

The acoustic block is not worthless. Cluster membership is the strongest
acoustic term at **−0.49**, and arousal fitted alone lands at **+0.16**. The
two sonic worlds do separate on the outcome: **18.2% vs 8.9%** return rates.

But the hold-out gain is **+0.012 with a 95% interval of [−0.019, +0.042]**.
That interval contains zero. A coefficient with the right sign and a plausible
size can still fail to buy ranking power, and separating those two things is
most of what this project does.

### Read the interval, not the point estimate

The demo's simulated listener was reconfigured three times as the profile
sharpened — from a generic six-genre library to a polarised two-pole one, then
from a 13-year history to an age-derived one, then to the account's **real
creation date** read from a Spotify export. **The acoustic point estimate moved
+0.000 → +0.019 → +0.023 → +0.012 across those four runs, and its interval
contained zero in all four.**

Two things follow, and they are the most transferable findings here:

- *How much acoustics help depends on how genre-polarised the library is.* Two
  distant scenes give the acoustic block real variance to exploit; one scene,
  however deep, does not. A single published number for "do audio features
  predict musical nostalgia" is reporting a property of somebody's library.
- *History length moves everything downstream.* Across 13.4, 7.6 and 10.4-year
  histories the unlabelable share ran 9% → 19% → 12.8% and the returner rate
  19.4% → 13.7% → 16.9%, purely because a fixed 635-day labelling cost is a
  different fraction of each. Getting the account's real start date right
  mattered more than any modelling choice made here.

Across all seven label definitions in [`sensitivity.csv`](outputs/sensitivity.csv)
the delta ranges **−0.012 to +0.015** and straddles zero throughout.

### What has been stable across every configuration

| | |
|---|---|
| Behavioural AUC | 0.76–0.79 across all four runs |
| Acoustic interval | contains zero in all four |
| Concentration under control | rejected every time (53–70% attenuation) |
| Library inside the bump window | 93–100%, and never ranks within it |
| `k` chosen by silhouette | 2, every time |

Those are the claims worth carrying out of this project. The point estimates
are not.

## The data

**The numbers above come from a simulated listener, not from a real account.**
A private Spotify history cannot be committed to a repository, which would make
every number here unverifiable and the code untestable. So the pipeline ships
with a listener it can invent — `simulate_listener.py`, 1,400 tracks and 38,258
streams over 10.4 years, deterministic from a seed.

**One number in it is real.** The account creation date, `2016-02-05`, is read
from `UserAttributes.json` in a Spotify "Account data" export. That bundle
carries no streaming history at all — no timestamps, no play counts — so it
cannot drive the analysis, but it does say when the account opened, and history
length turned out to be the binding constraint on everything downstream.
Override it with `--account-start`.

That buys two things and no more: the code is exercised end to end, and because
the simulator's true coefficients are written down, an estimate that recovers
something the simulator never put in is a visible bug. **It does not validate
the theory.** The generative process bakes in the effects the analysis then
goes looking for; a good result on it proves the pipeline runs.

Its six sonic worlds are shaped after a real stated taste — a rap/trap pole, a
UK house and electronic pole, and a DJ-sets world that exists specifically to
exercise the long-form path. **The artists are invented.** Only the scene
structure is borrowed, and nothing in the output should be read as a claim
about any real recording.

Three real inputs are supported, best first:

| Input | What it gives you | Script |
|---|---|---|
| **Extended Streaming History** (free GDPR export) | Every stream since the account opened, with timestamps and `ms_played`. The only input that supports the returner label. | `ingest_history.py` |
| **Web API** (Spotipy + a developer app) | Top tracks in three windows, saved tracks with `added_at`, the last 50 plays. Track metadata and *maybe* audio features. | `fetch_spotify.py` |
| **Simulated** | Nothing true. Runs the pipeline. | `simulate_listener.py` |

The export is the one to ask for. The Web API is generous about *what* you like
and stingy about *when* — it returns 50 recent plays, and this whole analysis is
about how listening is distributed over years.

### Audio features may simply not be available to you

On **27 November 2024** Spotify closed `/v1/audio-features`,
`/v1/audio-analysis`, `/v1/recommendations`, related-artists and 30-second
previews to applications created after that date. Apps that already held
extended quota kept access. A developer app you make today **will get 403** on
danceability, energy, valence and acousticness.

That is the brief's "CogSci twist" endpoint, so it is worth being blunt: for
most people starting this project now, the acoustic half is not fetchable from
Spotify at all. The pipeline treats acoustics as optional throughout — it asks,
records the answer, and runs either way, reporting which mode it ran in so an
acoustic-free result never gets to look like an acoustic one.
`fetch_spotify.py` prints the three ways to fill the gap (skip it; supply your
own CSV from an extractor like Essentia or librosa; get extended quota).

Given the finding above, the acoustic-free run loses about two points of AUC,
inside its own confidence interval.

## Running it

```bash
pip install -r memory-lane/requirements.txt

# demo — no credentials, no account, deterministic
python memory-lane/simulate_listener.py
python memory-lane/run_memory_lane.py

# your own history (recommended path)
python memory-lane/ingest_history.py ~/Downloads/my_spotify_data
python memory-lane/run_memory_lane.py --birth-year 1998

# your own account via the Web API
export SPOTIPY_CLIENT_ID=... SPOTIPY_CLIENT_SECRET=...
export SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
python memory-lane/fetch_spotify.py
python memory-lane/run_memory_lane.py --birth-year 1998

# how much of this depends on the definitions I chose
python memory-lane/sensitivity.py

# the playlist — dry run by default, and asks before writing
python memory-lane/make_playlist.py
python memory-lane/make_playlist.py --create
```

Deterministic: same seed, same numbers, byte-identical SVGs. Verified by
deleting `data/` and `outputs/`, regenerating and diffing.

`make_playlist.py` is the only script that changes your account. It prints what
it would create and stops; `--create` makes it ask first; playlists are private
unless you pass `--public`.

## Layout

```
psychology.py          the reminiscence bump and the acoustic hypothesis, cited
                       — every judgment the project makes, isolated in one file
simulate_listener.py   a synthetic 13-year history, so the pipeline is testable
ingest_history.py      parse a Spotify Extended Streaming History export
fetch_spotify.py       Spotipy ingest; degrades gracefully when audio features 403
run_memory_lane.py     label -> encoding features -> K-Means -> model -> figures
sensitivity.py         sweeps the four chosen constants and rebuilds the headline
make_playlist.py       the shortlist, as an actual playlist (opt-in)
docs/METHOD.md         definitions, leakage rules, and what this cannot know
outputs/metrics.json   every number quoted above
outputs/sensitivity.csv  the headline under seven label definitions
outputs/core_memory_tracks.csv   the shortlist
outputs/figures/       five SVGs, regenerated by run_memory_lane.py
```

## Method notes

- **No leakage.** Every model feature comes from the first 90 days after a
  track's first play. Total plays, last-played date and lifetime span all
  contain the answer and are all excluded. What the model sees is what was
  knowable within a season of first hearing a song.
- **Train on the old, score the new.** A track needs 635 days of observation
  (90 encoding + 365 dormancy + 180 to prove a return) before it can be
  labelled. Younger tracks are held out of training entirely rather than
  labelled negative — calling a six-month-old track "never came back" would be
  scoring it for being six months old. Those 124 held-out tracks are the
  deliverable: the modern songs, scored by a model fitted on songs whose
  verdict is already in. At 10.4 years of history that bucket holds 176 tracks,
  12.8% of the library.
- **Completion is capped at an eight-minute denominator,** with a separate
  `is_long_form` indicator, so DJ sets and live mixes are not scored as songs
  nobody finishes. See above — this was the largest single win in the project.
- **The playlist's artist cap relaxes rather than under-filling.** Two per
  artist assumes a broad library. Someone who listens to seven artists on
  repeat cannot fill thirty slots at two apiece, so the cap rises until the
  list fills and the applied value is reported in `metrics.json`. A 30-track
  list built at five per artist is a different object from one built at two,
  and the reader should be able to see which they got.
- **Logistic regression over a boosted tree,** deliberately. The output is an
  argument about why a song is on a playlist, and coefficients are legible in a
  way feature importances are not.
- **`arousal` is excluded from the joint model.** It is `0.6·energy +
  0.4·loudness`, a deterministic function of two predictors already in it, and
  including all three makes the coefficients meaningless. It is fitted alone
  and reported separately.
- **k is chosen by silhouette, not asserted.** It selected **k = 2**
  (silhouette 0.57) while the simulator generated six worlds. On overlapping
  acoustic blobs, K-Means finds the dominant axis and not the taxonomy.
- **Bootstrap the difference, not the two AUCs.** The interval is computed on
  the same resampled hold-out rows for both models, so it answers "did adding
  acoustics help" rather than "are these two numbers different".

## What this cannot know

Recorded in `psychology.py` and carried into every output, because the honest
limits of the method are part of the result:

- **Social context** — who you heard it with is a first-order driver of musical
  nostalgia and leaves no trace in a log.
- **Lyrical self-relevance** — `speechiness` detects spoken words, not whether
  the words meant anything. No proxy is used, because using one would be
  dressing up a guess.
- **Life events** — the bump is about developmental period, but a move or a
  loss binds music at any age.
- **Off-platform listening** — radio, live shows, a friend's aux cable, and
  everything before the account existed.
