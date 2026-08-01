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

**The answer, in short:** the psychology names the right era but does not rank
the tracks inside it, and the acoustics barely matter. Behaviour in a song's
first ninety days predicts return at **AUC 0.785**. Adding every acoustic
feature Spotify exposes moves that to **0.786** — a change of **+0.0004, 95% CI
[−0.029, +0.029]**. The fun part of the brief is the part that does not work.

## Findings

| | |
|---|---|
| Tracks that came back after a year of silence | **17.9%** |
| Median dormancy before a return | **1,054 days** (2.9 years) |
| Hold-out AUC, first-90-days behaviour | **0.785** |
| Hold-out AUC, behaviour + acoustics | **0.786** (Δ +0.0004, CI [−0.029, +0.029]) |
| Library first played inside the bump window (ages 10–28) | **93%** |
| Sonic worlds K-Means found (silhouette-selected) | **2** |

**The reminiscence bump is a claim about eras, not tracks.** It says music
encoded between roughly 10 and 28 binds hardest, and 93% of this library sits
inside that window — which is *why the project is interesting* and also why the
bump weight ranks nothing within it. Inside one year of one person's listening
it is near-constant. It is deliberately excluded from the per-track score
rather than folded in to make the model look more scientific.

**The most tempting behavioural lever was rejected.** Cramming a song into a
single fortnight looks like a strong negative signal — the top concentration
decile returns at 5% against 18% overall. But concentration correlates −0.58
with play count, and the coefficient falls from **−0.58 to −0.23** once volume
is held constant: a **61% attenuation**. Songs crammed into one fortnight
mostly aren't bound to a moment, they were played four times.

## What the acoustic result actually means

The acoustic coefficients are not zero and they point where the literature says
they should. Emotional intensity — distance from neutral valence — is the
strongest acoustic term in the joint model at **+0.40 log-odds per SD**, ahead
of every raw Spotify feature. Arousal, fitted on its own, comes in at **+0.07**.

They just don't buy any *discrimination*. A coefficient with the right sign and
a plausible size can still be worth nothing for ranking, and separating those
two things is most of what this project does. The hold-out interval is 0.058
wide, so any acoustic gain smaller than about 0.03 AUC would be invisible here
regardless of whether it exists. **"No detectable effect" is the finding.
"No effect" is not**, and the write-up does not claim it.

## The data

**The numbers above come from a simulated listener, not from a real account.**
A private Spotify history cannot be committed to a repository, which would make
every number here unverifiable and the code untestable. So the pipeline ships
with a listener it can invent — `simulate_listener.py`, 1,400 tracks and 38,761
streams over 13.4 years, deterministic from a seed.

That buys two things and no more: the code is exercised end to end, and because
the simulator's true coefficients are written down, an estimate that recovers
something the simulator never put in is a visible bug. **It does not validate
the theory.** The generative process bakes in the effects the analysis then
goes looking for; a good result on it proves the pipeline runs.

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

The headline finding is a mild consolation: the acoustic features add
approximately nothing anyway.

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

# the playlist — dry run by default, and asks before writing
python memory-lane/make_playlist.py
python memory-lane/make_playlist.py --create
```

Deterministic: same seed, same numbers, byte-identical SVGs. Verified by
deleting `outputs/`, regenerating from `simulate_listener.py` and diffing.

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
make_playlist.py       the shortlist, as an actual playlist (opt-in)
docs/METHOD.md         definitions, leakage rules, and what this cannot know
outputs/metrics.json   every number quoted above
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
  scoring it for being six months old. Those 134 held-out tracks are the
  deliverable: the modern songs, scored by a model fitted on songs whose
  verdict is already in.
- **Logistic regression over a boosted tree,** deliberately. The output is an
  argument about why a song is on a playlist, and coefficients are legible in a
  way feature importances are not.
- **`arousal` is excluded from the joint model.** It is `0.6·energy +
  0.4·loudness`, a deterministic function of two predictors already in it, and
  including all three makes the coefficients meaningless. It is fitted alone
  and reported separately.
- **k is chosen by silhouette, not asserted.** It selected **k = 2** —
  essentially the acoustic/electric axis — while the simulator generated six
  worlds. On overlapping acoustic blobs, K-Means finds the dominant axis and
  not the taxonomy. The clusters also don't separate keepers from forgettables
  (19% vs 15% return rate), which is the same negative result the AUC gives.
- **The playlist has an artist cap of 2.** A shortlist that is eleven songs by
  one band is a model telling you about one band. That failure only shows up
  when you look at the output as a playlist rather than as a ranking.
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
