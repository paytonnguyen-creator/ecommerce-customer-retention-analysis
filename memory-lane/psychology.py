"""
The music-psychology layer: what the literature actually claims, written down as
code so the claims can be argued with instead of absorbed.

WHY THIS FILE EXISTS SEPARATELY
-------------------------------
Every number in here is a JUDGMENT read off published research, not a quantity
estimated from the listener's own data. Mixing those two kinds of number in one
file is how a project ends up unable to say which of its conclusions came from
evidence and which came from the author. So the judgments live here, isolated
and cited, and `run_memory_lane.py` estimates everything else.

If you think the bump peaks at 20 rather than 17, change ONE constant below and
rerun. That is the whole point.

WHAT THE RESEARCH SUPPORTS
--------------------------
1. THE REMINISCENCE BUMP.  Autobiographical memory is over-represented for
   events encoded roughly between ages 10 and 30, peaking in the late teens
   (Rubin, Wetzler & Nebes 1986; Rubin & Schulkind 1997). For MUSIC the peak
   sits early in that range: Krumhansl & Zupnick (2013) put self-relevant
   musical memory around ages 14-22, and also document a *cascading* bump for
   music from the listener's parents' own bump years.

2. EXPOSURE.  Music-evoked autobiographical memories attach to songs the
   listener heard OFTEN, not songs they rated highest (Janata, Tomic & Rubin
   2007). Frequency of hearing beats stated preference.

3. AROUSAL AND EMOTION AT ENCODING.  Songs that evoke autobiographical memories
   are rated as more arousing and more emotional than matched controls
   (Jakubowski & Eerola 2022). This is the one strand that predicts from
   ACOUSTICS rather than behaviour, which makes it the interesting thing to
   test -- and, in this pipeline, the thing that mostly fails to replicate.

4. CONTEXTUAL DISTINCTIVENESS.  Memory favours the bounded and the unusual: a
   song welded to one summer beats a song played evenly for nine years. This
   one is not a music-specific finding, but it is the strongest *measurable*
   effect in a listening log, because "bounded to one period" is a shape you
   can compute from timestamps.

WHAT THE RESEARCH SUPPORTS THAT THIS PROJECT CANNOT MEASURE
-----------------------------------------------------------
Social context is a first-order driver of musical nostalgia -- who you were
with, whether you sang it together -- and a listening log contains no trace of
it. Lyrical self-relevance is likewise out of reach; `speechiness` measures the
presence of spoken words, not whether the words meant anything, and using it as
a proxy for lyrical resonance would be dressing up a guess. Both are recorded
here as known blind spots rather than approximated badly.

Citations
---------
Rubin, Wetzler & Nebes (1986), Autobiographical memory across the adult
    lifespan, in Rubin (ed.), *Autobiographical Memory*, CUP.
Rubin & Schulkind (1997), The distribution of autobiographical memories across
    the lifespan, *Memory & Cognition* 25(6).
Krumhansl & Zupnick (2013), Cascading reminiscence bumps in popular music,
    *Psychological Science* 24(10).
Janata, Tomic & Rubin (2007), Characterisation of music-evoked autobiographical
    memories, *Memory* 15(8).
Jakubowski & Eerola (2022), Music-evoked autobiographical memories in everyday
    life, *Psychology of Music* 50(2).
"""

from __future__ import annotations

import numpy as np

# ── The reminiscence-bump curve ──────────────────────────────────────────────
# A smooth rise into the bump and a slower decay out of it. These five numbers
# are the entire psychological model, and all five are arguable.
BUMP_ONSET = 8.0        # age at which music starts encoding autobiographically
BUMP_ONSET_WIDTH = 1.6  # how sharply it switches on
BUMP_OFFSET = 32.0      # age by which encoding has mostly returned to baseline
BUMP_OFFSET_WIDTH = 3.2  # how gradually it switches off
ADULT_FLOOR = 0.25      # adult encoding is weaker, not absent


def _sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-x))


def encoding_weight(age: np.ndarray | float) -> np.ndarray | float:
    """
    Relative strength with which music heard at `age` is expected to bind to
    autobiographical memory. Peaks ~0.99 in the late teens, ~0.74 at 30, and
    settles toward the adult floor after that.

    This is a RELATIVE weight on a 0-1 scale, not a probability of anything. It
    is used for one job only: comparing eras of a listening history against each
    other. Within a single year of one person's listening it is near-constant
    and therefore useless for ranking tracks -- a limitation that matters enough
    to be reported in the output rather than buried here.
    """
    age = np.asarray(age, dtype=float)
    rise = _sigmoid((age - BUMP_ONSET) / BUMP_ONSET_WIDTH)
    fall = _sigmoid((BUMP_OFFSET - age) / BUMP_OFFSET_WIDTH)
    return ADULT_FLOOR + (1.0 - ADULT_FLOOR) * rise * fall


def bump_window(threshold: float = 0.85) -> tuple[float, float]:
    """The age range over which encoding weight clears `threshold`."""
    ages = np.arange(0, 80, 0.05)
    inside = ages[encoding_weight(ages) >= threshold]
    return (float(inside.min()), float(inside.max())) if len(inside) else (np.nan, np.nan)


# ── The acoustic hypothesis ──────────────────────────────────────────────────
# Strand 3 above, stated precisely enough to be wrong. Arousal is the construct
# the literature points at; Spotify does not expose "arousal", so it is built
# from the two features that most nearly stand in for it, and the substitution
# is declared rather than assumed away.
AROUSAL_PROXY = {"energy": 0.6, "loudness_norm": 0.4}

# Emotional intensity, not pleasantness: a song at either end of the valence
# scale is more memorable than one in the middle, so valence enters as distance
# from neutral rather than as its raw value.
VALENCE_INTENSITY_CENTRE = 0.5

ACOUSTIC_FEATURES = [
    "danceability", "energy", "valence", "acousticness",
    "speechiness", "instrumentalness", "tempo", "loudness",
]

# Features the pipeline will use if present but never requires. Spotify closed
# /v1/audio-features to new applications in November 2024, so any of these may
# be absent; see docs/METHOD.md.
OPTIONAL_ACOUSTIC = set(ACOUSTIC_FEATURES)


def arousal_index(df) -> "np.ndarray":
    """
    Composite arousal proxy in [0, 1]. Requires `energy` and `loudness`;
    returns NaN if the columns are missing, which is the honest answer when
    the audio-features endpoint is unavailable.
    """
    if not {"energy", "loudness"}.issubset(df.columns):
        return np.full(len(df), np.nan)
    # Spotify loudness is dBFS, roughly -60..0. Map to 0-1 without clipping the
    # informative range.
    loudness_norm = ((df["loudness"].to_numpy() + 60.0) / 60.0).clip(0, 1)
    return (AROUSAL_PROXY["energy"] * df["energy"].to_numpy()
            + AROUSAL_PROXY["loudness_norm"] * loudness_norm)


def valence_intensity(df) -> "np.ndarray":
    """Distance from emotionally neutral, scaled to [0, 1]."""
    if "valence" not in df.columns:
        return np.full(len(df), np.nan)
    return np.abs(df["valence"].to_numpy() - VALENCE_INTENSITY_CENTRE) * 2.0


# ── Blind spots, carried into the output ─────────────────────────────────────
# Written here so the report can state them without the reporting code having
# to know any psychology.
BLIND_SPOTS = [
    ("Social context",
     "Who you heard it with is a first-order driver of musical nostalgia and "
     "leaves no trace in a listening log."),
    ("Lyrical self-relevance",
     "`speechiness` detects spoken words, not whether the words meant "
     "anything. No proxy is used."),
    ("Life events",
     "The bump is about developmental period, but a move, a breakup or a loss "
     "binds music at any age. Unobservable here."),
    ("Off-platform listening",
     "Radio, live shows, a friend's playlist and anything played before the "
     "account existed are invisible."),
]
