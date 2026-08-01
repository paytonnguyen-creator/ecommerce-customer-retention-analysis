"""
Memory Lane: which of the songs I am listening to now will still be pulling on
me in twenty years?

THE QUESTION, AND WHY IT NEEDS RESTATING BEFORE IT CAN BE ANSWERED
------------------------------------------------------------------
"Will this song give me chills in 2046" has no ground truth. Nobody holds a
labelled dataset of songs that turned out to be core memories, mine least of
all, and a supervised model without labels is astrology with a train/test
split. So the question is replaced by one the data can actually answer:

    Which songs do I come back to after I have stopped listening to them?

That is a real, observable behaviour with a real label. A track counts as a
RETURNER if it went dormant for a year or more and then came back into
rotation for at least three more plays. It is not nostalgia — it is the
behavioural shadow nostalgia casts in a listening log, and unlike nostalgia it
can be measured, held out, and scored.

The design then falls out of the data's own shape:

    TRAIN on old tracks, which have had time to prove themselves either way.
    SCORE the recent tracks, which have not.

That split is the point rather than a technicality. A track first played six
months ago cannot yet have been dormant for a year, so calling it a
non-returner would be labelling it for being new. Those tracks are held out of
training entirely and become the thing the project is actually about: the
modern songs, scored by a model fitted on the ones whose verdict is already in.

NO LEAKAGE
----------
Every model feature comes from the first 90 days after a track's first play.
Total play count, last-played date, span — all of them contain the answer, and
all of them are excluded. What the model sees is what was knowable within a
season of hearing a song for the first time.

WHAT THE PSYCHOLOGY BUYS, AND WHAT IT DOESN'T
---------------------------------------------
The reminiscence bump says music encoded in the teens and early twenties binds
hardest. That is a strong claim about which ERA of a history matters and a
silent one about which TRACK inside an era matters — within one year of one
person's listening the bump weight is near-constant and ranks nothing. So it is
used where it applies (weighting eras, framing the finding) and not smuggled
into the per-track score. This is reported rather than glossed, because the
gap between "the literature supports the concept" and "the literature ranks my
tracks" is where this kind of project usually goes wrong.

The testable acoustic claim is narrower: memory-evoking songs are rated more
arousing and more emotionally intense. That one gets a clean test — fit the
model with behaviour alone, then with behaviour plus acoustics, and bootstrap
the difference in hold-out AUC. Whatever that difference turns out to be is the
headline, including if it is nothing.

Run:    python memory-lane/simulate_listener.py     (or fetch_spotify.py / ingest_history.py)
        python memory-lane/run_memory_lane.py
Writes: memory-lane/outputs/metrics.json
        memory-lane/outputs/core_memory_tracks.csv
        memory-lane/outputs/figures/*.svg
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, roc_curve, silhouette_score
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parent))
import psychology as psy  # noqa: E402

HERE = Path(__file__).resolve().parent
DATA, OUT, FIGS = HERE / "data", HERE / "outputs", HERE / "outputs/figures"

# ── The four definitions the whole analysis rests on ─────────────────────────
ENCODING_WINDOW = 90   # days after first play in which features may be measured
DORMANCY = 365         # a silence of at least this long counts as having stopped
RETURN_PLAYS = 3       # plays after that silence needed to count as coming back
OBSERVE_AFTER = 180    # time a track needs after the dormancy window to prove it
LABELABLE_AGE = ENCODING_WINDOW + DORMANCY + OBSERVE_AFTER  # 635 days

PLAY_FLOOR_MS = 30_000
MAX_PER_ARTIST = 2     # playlist diversity cap
SHORTLIST = 30
SEED = 42

# Long-form content breaks fractional completion. A 70-minute DJ set played for
# twenty minutes scores 0.28 -- the same as bailing on a three-minute track
# after fifty seconds -- and since completion is one of the model's strongest
# features, that quietly pushes every mix and live set to the bottom of the
# shortlist. Engagement with long-form is an ABSOLUTE amount of time, not a
# fraction, so the denominator is capped: past the reference length, staying is
# what counts, not finishing.
COMPLETION_REFERENCE_MS = 8 * 60 * 1000   # a generously long "normal" track
LONG_FORM_MS = 15 * 60 * 1000             # mixes, sets, live recordings

# Validated categorical palette, slots 1-3 (checked with the dataviz validator
# in both modes; aqua sits under 3:1 on the light surface so it is only ever
# used with a direct label attached).
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID, GHOST = "#14161a", "#6b7078", "#e4e6ea", "#c9ccd2"

plt.rcParams.update({
    "figure.dpi": 110, "font.size": 11, "font.family": "DejaVu Sans",
    "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "svg.fonttype": "none",
    "svg.hashsalt": "memory-lane",  # fixed salt -> byte-identical reruns
})


# ── 1. Load ──────────────────────────────────────────────────────────────────
def load() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    for f in ("streams.csv", "tracks.csv", "source.json"):
        if not (DATA / f).exists():
            sys.exit(f"Missing {DATA / f}.\nRun one of:\n"
                     f"  python memory-lane/simulate_listener.py      (demo)\n"
                     f"  python memory-lane/fetch_spotify.py          (your account)\n"
                     f"  python memory-lane/ingest_history.py <dir>   (your export)")

    source = json.loads((DATA / "source.json").read_text())
    tracks = pd.read_csv(DATA / "tracks.csv")
    streams = pd.read_csv(DATA / "streams.csv")
    streams["played_at"] = (pd.to_datetime(streams["played_at"], format="mixed",
                                           utc=True).dt.tz_localize(None))
    streams = streams.dropna(subset=["played_at", "track_id"])
    return tracks, streams, source


def acoustic_columns(tracks: pd.DataFrame) -> list[str]:
    """Whatever acoustic features actually arrived. Possibly none."""
    return [c for c in psy.ACOUSTIC_FEATURES
            if c in tracks.columns and tracks[c].notna().mean() > 0.5]


# ── 2. Label: who came back? ─────────────────────────────────────────────────
def label_returners(streams: pd.DataFrame, data_end: pd.Timestamp) -> pd.DataFrame:
    """
    A returner went quiet for DORMANCY days and then came back for at least
    RETURN_PLAYS more plays. Tracks too young to have had the chance are marked
    unlabelable rather than labelled negative -- scoring a six-month-old track
    as "never came back" would be scoring it for being six months old.
    """
    plays = streams[streams["ms_played"] >= PLAY_FLOOR_MS]
    plays = plays.sort_values(["track_id", "played_at"])

    out = []
    for tid, g in plays.groupby("track_id", sort=False):
        d = g["played_at"].to_numpy()
        first = d[0]
        if len(d) > 1:
            gaps = np.diff(d).astype("timedelta64[D]").astype(int)
            i = int(np.argmax(gaps))
            max_gap, after = int(gaps[i]), len(d) - (i + 1)
        else:
            max_gap, after = 0, 0
        out.append((tid, pd.Timestamp(first), pd.Timestamp(d[-1]), len(d),
                    max_gap, after))

    lab = pd.DataFrame(out, columns=["track_id", "first_play", "last_play",
                                     "total_plays", "max_gap_days",
                                     "plays_after_gap"])
    lab["returner"] = ((lab.max_gap_days >= DORMANCY)
                       & (lab.plays_after_gap >= RETURN_PLAYS)).astype(int)
    lab["observed_days"] = (data_end - lab.first_play).dt.days
    lab["labelable"] = lab.observed_days >= LABELABLE_AGE
    return lab


# ── 3. Encoding-window features (nothing the future could tell you) ──────────
def encoding_features(streams: pd.DataFrame, tracks: pd.DataFrame,
                      lab: pd.DataFrame, birth_year: int) -> pd.DataFrame:
    s = streams.merge(lab[["track_id", "first_play"]], on="track_id")
    s["day_offset"] = (s["played_at"] - s["first_play"]).dt.days
    win = s[(s.day_offset >= 0) & (s.day_offset < ENCODING_WINDOW)].copy()

    dur = tracks.set_index("track_id")["duration_ms"] if "duration_ms" in tracks else None
    if dur is not None:
        track_dur = win["track_id"].map(dur)
        denom = np.minimum(track_dur, COMPLETION_REFERENCE_MS)
        win["completion"] = (win["ms_played"] / denom).clip(0, 1)
    else:
        win["completion"] = np.nan

    real = win[win.ms_played >= PLAY_FLOOR_MS]

    agg = real.groupby("track_id").agg(
        enc_plays=("played_at", "size"),
        enc_active_days=("played_at", lambda x: x.dt.normalize().nunique()),
        enc_span_days=("day_offset", lambda x: int(x.max() - x.min())),
        enc_completion=("completion", "mean"),
    )
    agg["enc_skip_rate"] = (
        win.groupby("track_id").size().sub(agg.enc_plays, fill_value=0)
        / win.groupby("track_id").size()
    ).fillna(0)

    # Distinctiveness: how much of the encoding window's listening piled into
    # its densest fortnight. A song bound to two weeks of one autumn scores
    # high; a song trickled evenly across the season scores low.
    fortnight = (real.assign(slot=real.day_offset // 14)
                     .groupby(["track_id", "slot"]).size()
                     .groupby("track_id").agg(["max", "sum"]))
    agg["enc_concentration"] = (fortnight["max"] / fortnight["sum"]).reindex(agg.index)

    per_day = (real.assign(day=real.day_offset)
                   .groupby(["track_id", "day"]).size()
                   .groupby("track_id").max())
    agg["enc_peak_day_share"] = (per_day / agg.enc_plays).reindex(agg.index)

    feat = lab.merge(agg.reset_index(), on="track_id", how="left")
    for c in ["enc_plays", "enc_active_days", "enc_span_days", "enc_skip_rate"]:
        feat[c] = feat[c].fillna(0)
    for c in ["enc_completion", "enc_concentration", "enc_peak_day_share"]:
        feat[c] = feat[c].fillna(feat[c].median())

    feat["log_enc_plays"] = np.log1p(feat.enc_plays)
    feat["age_at_first_play"] = (feat.first_play.dt.year - birth_year
                                 + feat.first_play.dt.dayofyear / 365.25)
    feat["bump_weight"] = psy.encoding_weight(feat.age_at_first_play)

    keep = [c for c in ["name", "artist", "duration_ms", "popularity",
                        "release_date", "true_world", "true_returner",
                        *psy.ACOUSTIC_FEATURES] if c in tracks.columns]
    feat = feat.merge(tracks[["track_id", *keep]], on="track_id", how="left")

    # Kept as an explicit indicator rather than folded into completion, so a mix
    # is visibly a different kind of object to the model instead of a song that
    # nobody finishes.
    if "duration_ms" in feat.columns:
        feat["is_long_form"] = (feat.duration_ms >= LONG_FORM_MS).astype(float)

    if "release_date" in feat.columns:
        rel = pd.to_datetime(feat.release_date, format="mixed", errors="coerce")
        feat["catalogue_age_years"] = ((feat.first_play - rel).dt.days / 365.25).clip(lower=0)
        feat["catalogue_age_years"] = feat.catalogue_age_years.fillna(
            feat.catalogue_age_years.median())
    return feat


BEHAVIOURAL = ["log_enc_plays", "enc_active_days", "enc_span_days",
               "enc_completion", "enc_skip_rate", "enc_concentration",
               "enc_peak_day_share", "age_at_first_play"]


# ── 4. Sonic worlds ──────────────────────────────────────────────────────────
def cluster_worlds(feat: pd.DataFrame, cols: list[str]) -> tuple[pd.DataFrame, dict]:
    """
    K-Means over acoustic space. k is chosen by silhouette rather than asserted,
    and the clusters are named from their own centroids so the labels are
    derived rather than imposed.
    """
    X = feat[cols].to_numpy(dtype=float)
    Z = (X - X.mean(0)) / X.std(0)

    scores = {}
    for k in range(2, 9):
        km = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(Z)
        scores[k] = float(silhouette_score(Z, km.labels_, random_state=SEED))
    best_k = max(scores, key=scores.get)

    km = KMeans(n_clusters=best_k, n_init=10, random_state=SEED).fit(Z)
    feat["cluster"] = km.labels_

    names, profiles = {}, []
    for c in range(best_k):
        centroid = Z[km.labels_ == c].mean(0)
        order = np.argsort(-np.abs(centroid))[:2]
        parts = [f"{'high' if centroid[i] > 0 else 'low'} {cols[i]}" for i in order]
        names[c] = " · ".join(parts)
        profiles.append({
            "cluster": int(c), "label": names[c],
            "tracks": int((km.labels_ == c).sum()),
            **{f"mean_{cols[i]}": float(X[km.labels_ == c, i].mean())
               for i in range(len(cols))},
        })
    feat["world"] = feat.cluster.map(names)

    pca = PCA(n_components=2, random_state=SEED).fit(Z)
    feat[["pc1", "pc2"]] = pca.transform(Z)

    return feat, {
        "k": int(best_k),
        "silhouette_by_k": {str(k): round(v, 4) for k, v in scores.items()},
        "silhouette": round(scores[best_k], 4),
        "explained_variance_pc1_pc2": [float(v) for v in pca.explained_variance_ratio_],
        "profiles": profiles,
    }


# ── 5. Does the acoustics actually help? ─────────────────────────────────────
def _fit(X: pd.DataFrame, y: pd.Series, idx_tr, idx_te):
    m = LogisticRegression(max_iter=4000).fit(X.iloc[idx_tr], y.iloc[idx_tr])
    p = m.predict_proba(X.iloc[idx_te])[:, 1]
    return m, p, float(roc_auc_score(y.iloc[idx_te], p))


def compare_models(feat: pd.DataFrame, acoustic: list[str],
                   have_acoustic: bool) -> dict:
    """
    The one clean test in the project. Behaviour alone, then behaviour plus
    acoustics, same split, and a bootstrap interval on the difference so the
    gap can be read as real or as noise instead of being eyeballed.
    """
    d = feat[feat.labelable].reset_index(drop=True)
    y = d["returner"]

    def z(frame):
        return (frame - frame.mean()) / frame.std().replace(0, 1)

    Xb = z(d[BEHAVIOURAL].astype(float))
    if "catalogue_age_years" in d.columns:
        Xb["catalogue_age_years"] = z(d[["catalogue_age_years"]].astype(float)).iloc[:, 0]
    if "is_long_form" in d.columns:
        Xb["is_long_form"] = d["is_long_form"].astype(float).to_numpy()  # already 0/1

    idx_tr, idx_te = train_test_split(np.arange(len(d)), test_size=0.30,
                                      random_state=SEED, stratify=y)
    m_b, p_b, auc_b = _fit(Xb, y, idx_tr, idx_te)

    res = {
        "n_labelable": int(len(d)), "n_train": len(idx_tr), "n_test": len(idx_te),
        "base_rate": float(y.mean()),
        "behavioural_features": list(Xb.columns),
        "auc_behaviour": auc_b,
        "have_acoustic": have_acoustic,
    }

    if not have_acoustic:
        res.update({
            "auc_behaviour_plus_acoustic": None,
            "auc_delta": None,
            "note": ("No acoustic features available -- Spotify closed "
                     "/v1/audio-features to new apps on 2024-11-27. The "
                     "acoustic hypothesis was not tested in this run."),
        })
        res["_model"], res["_features"], res["_roc"] = m_b, Xb.columns, roc_curve(
            y.iloc[idx_te], p_b)
        res["_roc_acoustic"] = None
        res["coefficients"] = _coefs(m_b, Xb.columns)
        return res

    # `arousal` is 0.6*energy + 0.4*normalised loudness -- a deterministic
    # function of two predictors that are already in the block. Putting all
    # three in makes the three coefficients fight over one signal and none of
    # them means anything afterwards. It is kept out of the joint model and
    # fitted on its own instead, which is the only way its number stays
    # readable. `valence_intensity` is a NON-linear transform of valence
    # (distance from neutral), so that pair is not collinear and both stay.
    a = d[acoustic].astype(float).copy()
    a["valence_intensity"] = psy.valence_intensity(d)
    a = a.dropna(axis=1, how="all")
    Xa = pd.concat([Xb, z(a)], axis=1)
    Xa = pd.concat([Xa, pd.get_dummies(d.cluster, prefix="world", dtype=float)
                    .iloc[:, 1:]], axis=1)

    m_a, p_a, auc_a = _fit(Xa, y, idx_tr, idx_te)

    arousal = psy.arousal_index(d)
    solo = None
    if np.isfinite(arousal).all():
        solo_X = pd.DataFrame({"z_arousal": (arousal - arousal.mean()) / arousal.std()})
        solo = float(LogisticRegression(max_iter=4000)
                     .fit(solo_X, y).coef_[0][0])

    # Bootstrap the DIFFERENCE on the same resampled test rows, so the paired
    # structure is preserved and the interval answers "did adding acoustics
    # help" rather than "are these two AUCs different numbers".
    rng = np.random.default_rng(SEED)
    y_te = y.iloc[idx_te].to_numpy()
    deltas = []
    for _ in range(2000):
        s = rng.integers(0, len(y_te), len(y_te))
        if len(np.unique(y_te[s])) < 2:
            continue
        deltas.append(roc_auc_score(y_te[s], p_a[s]) - roc_auc_score(y_te[s], p_b[s]))
    lo, hi = np.percentile(deltas, [2.5, 97.5])

    res.update({
        "acoustic_features": [c for c in Xa.columns if c not in Xb.columns],
        "arousal_coef_alone": solo,
        "arousal_note": ("Excluded from the joint model: it is a deterministic "
                         "function of energy and loudness, which are both in it. "
                         "Reported here on its own."),
        "auc_behaviour_plus_acoustic": auc_a,
        "auc_delta": auc_a - auc_b,
        "auc_delta_ci95": [float(lo), float(hi)],
        "auc_delta_bootstrap_n": len(deltas),
        "acoustic_helps": bool(lo > 0),
        "smallest_detectable_gain": float(hi),
        "power_note": (
            f"With {len(y_te)} hold-out tracks the interval is {hi - lo:.3f} wide, "
            f"so any acoustic gain smaller than about {hi:+.3f} AUC would be "
            f"invisible to this test. 'No detectable effect' is the correct "
            f"reading; 'no effect' is not."),
        "coefficients": _coefs(m_a, Xa.columns),
    })
    res["_model"], res["_features"] = m_a, Xa.columns
    res["_roc"], res["_roc_acoustic"] = roc_curve(y_te, p_b), roc_curve(y_te, p_a)
    res["_train_frame"] = Xa
    return res


def confound_check(feat: pd.DataFrame, target: str = "enc_concentration",
                   control: str = "log_enc_plays") -> dict:
    """
    A song crammed into a single fortnight might be bound to a moment -- or it
    might simply have been played four times. Those two stories leave the same
    shape in the data, and one of them is a finding while the other is an
    artefact of the denominator.

    So concentration gets the treatment: fit it alone, fit it with play count
    held constant, and report how much of it survives. A coefficient that
    collapses under control is a coefficient that was measuring the control.
    """
    d = feat[feat.labelable]
    z = lambda s: (s - s.mean()) / s.std().replace(0, 1)
    y = d["returner"]

    alone = LogisticRegression(max_iter=4000).fit(z(d[[target]].astype(float)), y)
    both = LogisticRegression(max_iter=4000).fit(
        z(d[[target, control]].astype(float)), y)
    a, b = float(alone.coef_[0][0]), float(both.coef_[0][0])

    return {
        "feature": target, "control": control,
        "correlation": float(d[target].corr(d[control])),
        "coef_alone": round(a, 4), "coef_controlled": round(b, 4),
        "attenuation_pct": round((1 - abs(b) / abs(a)) * 100, 1) if a else None,
        "survives_control": bool(a * b > 0 and abs(b) >= 0.5 * abs(a)),
    }


def _coefs(model, cols) -> list[dict]:
    return (pd.DataFrame({"feature": list(cols), "coef": model.coef_[0]})
            .assign(odds_ratio=lambda t: np.exp(t.coef))
            .sort_values("coef", key=abs, ascending=False)
            .round(4).to_dict("records"))


# ── 6. Score the modern tracks ───────────────────────────────────────────────
def score_recent(feat: pd.DataFrame, res: dict, acoustic: list[str],
                 have_acoustic: bool) -> pd.DataFrame:
    """
    Apply the fitted model to the tracks that are too new to be labelled. This
    is the deliverable: the songs whose verdict is not yet in, ranked by how
    closely their first ninety days resemble the first ninety days of songs
    that turned out to be returners.
    """
    train = feat[feat.labelable]
    new = feat[~feat.labelable].copy()
    if new.empty:
        return new

    def z(frame, ref):
        return (frame - ref.mean()) / ref.std().replace(0, 1)

    cols_b = [c for c in BEHAVIOURAL]
    if "catalogue_age_years" in feat.columns:
        cols_b = cols_b + ["catalogue_age_years"]
    X = z(new[cols_b].astype(float), train[cols_b].astype(float))
    if "is_long_form" in feat.columns:
        X["is_long_form"] = new["is_long_form"].astype(float).to_numpy()

    if have_acoustic:
        a_new, a_ref = new[acoustic].astype(float).copy(), train[acoustic].astype(float).copy()
        for frame, src in ((a_new, new), (a_ref, train)):
            frame["valence_intensity"] = psy.valence_intensity(src)  # arousal is
            # deliberately absent -- see the collinearity note in compare_models
        a_new, a_ref = a_new.dropna(axis=1, how="all"), a_ref.dropna(axis=1, how="all")
        X = pd.concat([X, z(a_new, a_ref)], axis=1)
        dummies = pd.get_dummies(new.cluster, prefix="world", dtype=float)
        X = pd.concat([X, dummies], axis=1)

    X = X.reindex(columns=list(res["_features"]), fill_value=0.0).fillna(0.0)
    new["memory_lane_index"] = res["_model"].predict_proba(X)[:, 1] * 100
    return new.sort_values("memory_lane_index", ascending=False)


def shortlist(scored: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Top N by index, but no more than MAX_PER_ARTIST per artist. A playlist that
    is eleven songs by one band is a model telling you about one band, not
    about eleven memories -- and it is the kind of failure that only shows up
    once you look at the output as a playlist rather than as a ranking.

    A hard cap assumes a broad library, which is an assumption a lot of people
    break: someone who listens to seven artists on repeat cannot fill thirty
    slots at two apiece. So the cap RELAXES rather than silently returning a
    short playlist, and the relaxation is reported -- a 30-track list built at
    four per artist is a different object from one built at two, and the reader
    should be able to see which they got.
    """
    if "artist" not in scored.columns:
        return scored.head(SHORTLIST), {"artist_cap": None,
                                        "reason": "no artist column"}

    def pick(cap: int) -> list:
        chosen, counts = [], {}
        for row in scored.itertuples():
            a = getattr(row, "artist", "?")
            if counts.get(a, 0) >= cap:
                continue
            counts[a] = counts.get(a, 0) + 1
            chosen.append(row.Index)
            if len(chosen) >= SHORTLIST:
                break
        return chosen

    cap = MAX_PER_ARTIST
    picked = pick(cap)
    while len(picked) < SHORTLIST and cap < SHORTLIST:
        cap += 1
        picked = pick(cap)

    log = {
        "artist_cap_requested": MAX_PER_ARTIST,
        "artist_cap_applied": cap,
        "distinct_artists_in_scoring_set": int(scored.artist.nunique()),
        "distinct_artists_on_shortlist": int(scored.loc[picked].artist.nunique()),
        "tracks": len(picked),
        "cap_relaxed": cap > MAX_PER_ARTIST,
    }
    if log["cap_relaxed"]:
        log["note"] = (
            f"Only {log['distinct_artists_in_scoring_set']} artists have "
            f"recent tracks, so {MAX_PER_ARTIST} per artist could not fill "
            f"{SHORTLIST} slots. The cap was raised to {cap}. A concentrated "
            f"library gives a concentrated playlist; that is the library "
            f"talking, not the model.")
    return scored.loc[picked], log


# ── 7. Figures ───────────────────────────────────────────────────────────────
def _save(fig, name):
    # metadata Date=None strips the embedded timestamp; with the fixed hashsalt
    # this makes reruns byte-identical, so the figures are verifiable output
    # rather than something that might have been touched up by hand.
    fig.savefig(FIGS / name, format="svg", bbox_inches="tight", transparent=True,
                metadata={"Date": None})
    plt.close(fig)


def fig_bump(feat: pd.DataFrame) -> dict:
    """Two panels on a shared age axis -- never two scales on one axis."""
    ages = np.arange(5, 45, 0.1)
    w = psy.encoding_weight(ages)
    lo, hi = psy.bump_window(0.85)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 4.6), sharex=True,
                                   gridspec_kw={"height_ratios": [1, 1.1],
                                                "hspace": 0.18})
    ax1.axvspan(lo, hi, color=BLUE, alpha=0.07, lw=0)
    ax1.plot(ages, w, color=BLUE, lw=2)
    ax1.set_ylabel("Encoding weight")
    ax1.set_ylim(0, 1.12)
    ax1.grid(axis="y", color=GRID, lw=1); ax1.set_axisbelow(True)
    ax1.annotate(f"bump window · ages {lo:.0f}–{hi:.0f}", xy=((lo + hi) / 2, 0.14),
                 ha="center", va="bottom", color=MUTED, fontsize=9.5)
    ax1.set_title("The literature says when music binds. My history says what "
                  "was playing.", color=INK, fontsize=12.5, loc="left", pad=10)

    bins = np.arange(5, 45, 1)
    share = (np.histogram(feat.age_at_first_play.dropna(), bins=bins)[0]
             / max(len(feat), 1) * 100)
    inside = [(lo <= b < hi) for b in bins[:-1]]
    ax2.bar(bins[:-1] + 0.5, share, width=0.82,
            color=[BLUE if i else GHOST for i in inside])
    ax2.set_ylabel("Share of library (%)")
    ax2.set_xlabel("My age when I first played the track")
    ax2.grid(axis="y", color=GRID, lw=1); ax2.set_axisbelow(True)
    ax2.set_xlim(5, 45)

    covered = float(feat.age_at_first_play.between(lo, hi).mean())
    ax2.annotate(f"{covered:.0%} of the library was first played inside the window",
                 xy=(0.985, 0.9), xycoords="axes fraction", ha="right",
                 color=INK, fontsize=10)
    _save(fig, "reminiscence_bump.svg")
    return {"bump_window": [lo, hi], "share_of_library_in_bump": covered,
            "median_age_at_first_play": float(feat.age_at_first_play.median())}


def fig_worlds(feat: pd.DataFrame, info: dict):
    """
    Small multiples, not a six-colour scatter. Six categorical hues cannot be
    told apart pairwise under colour-vision deficiency at scatter density, so
    identity is carried by facet position with one highlight hue instead.
    """
    k = info["k"]
    ncol = min(3, k)
    nrow = int(np.ceil(k / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(3.0 * ncol, 2.7 * nrow),
                             sharex=True, sharey=True)
    axes = np.atleast_1d(axes).ravel()

    rate = feat.loc[feat.labelable].groupby("cluster")["returner"].mean()
    for c in range(k):
        ax = axes[c]
        m = feat.cluster == c
        ax.scatter(feat.loc[~m, "pc1"], feat.loc[~m, "pc2"], s=5, color=GHOST,
                   lw=0, alpha=0.55)
        ax.scatter(feat.loc[m, "pc1"], feat.loc[m, "pc2"], s=8, color=BLUE, lw=0)
        label = info["profiles"][c]["label"].replace(" · ", "\n")
        r = rate.get(c, np.nan)
        ax.set_title(f"{label}\n{m.sum()} tracks · {r:.0%} returned"
                     if pd.notna(r) else f"{label}\n{m.sum()} tracks",
                     fontsize=9.5, color=INK, loc="left", pad=6)
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color(GRID)
        ax.spines["top"].set_visible(True); ax.spines["right"].set_visible(True)
    for ax in axes[k:]:
        ax.axis("off")

    # The verdict is read off the clusters rather than asserted -- a title that
    # states a finding has to be recomputed when the finding changes.
    spread = (rate.max() - rate.min()) * 100 if len(rate) > 1 else 0.0
    verdict = (f"they split {rate.min():.0%}/{rate.max():.0%} on coming back"
               if spread >= 5 else
               "they do not sort into keepers and forgettables")
    fig.suptitle(f"K-Means found {k} sonic worlds (silhouette {info['silhouette']:.2f}) "
                 f"— {verdict}",
                 color=INK, fontsize=12.5, x=0.02, ha="left", y=1.0)
    fig.tight_layout()
    _save(fig, "sonic_worlds.svg")


def fig_roc(res: dict):
    fig, ax = plt.subplots(figsize=(5.0, 4.4))
    ax.plot([0, 1], [0, 1], color=MUTED, ls="--", lw=1)

    # The two curves sit on top of each other, which is the finding. Labels go
    # in the legend rather than beside the lines -- direct labels on
    # indistinguishable curves collide and imply a separation that is not there.
    fpr, tpr, _ = res["_roc"]
    ax.plot(fpr, tpr, color=BLUE, lw=2,
            label=f"Behaviour only — AUC {res['auc_behaviour']:.3f}")

    if res.get("_roc_acoustic") is not None:
        fpr2, tpr2, _ = res["_roc_acoustic"]
        ax.plot(fpr2, tpr2, color=ORANGE, lw=2,
                label=f"+ acoustic features — AUC "
                      f"{res['auc_behaviour_plus_acoustic']:.3f}")
        d = res["auc_delta"]
        lo, hi = res["auc_delta_ci95"]
        # Three outcomes, not two. An interval that contains zero around a
        # visibly positive point estimate is not the same claim as one centred
        # on nothing, and collapsing them would overstate the negative result.
        if lo > 0:
            verdict = "a real gain"
        elif hi < abs(lo):
            verdict = "indistinguishable from nothing"
        else:
            verdict = "positive, but the interval still contains zero"
        ax.set_title(f"Acoustics move AUC by {d:+.3f} [{lo:+.3f}, {hi:+.3f}]"
                     f" — {verdict}", color=INK, fontsize=12, loc="left", pad=12)
    else:
        ax.set_title("Hold-out ROC — behaviour only (acoustics unavailable)",
                     color=INK, fontsize=12.5, loc="left", pad=12)

    ax.legend(loc="lower right", frameon=False, fontsize=9.5)
    ax.set_xlabel("False positive rate"); ax.set_ylabel("True positive rate")
    ax.grid(color=GRID, lw=1); ax.set_axisbelow(True)
    _save(fig, "acoustics_vs_behaviour.svg")


def fig_distinctiveness(feat: pd.DataFrame, conf: dict) -> list[dict]:
    d = feat[feat.labelable].copy()
    d["decile"] = pd.qcut(d.enc_concentration.rank(method="first"), 10,
                          labels=False) + 1
    g = d.groupby("decile").agg(rate=("returner", "mean"),
                                conc=("enc_concentration", "median"),
                                n=("returner", "size")).reset_index()

    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.plot(g.decile, g.rate * 100, color=BLUE, lw=2, marker="o", ms=7,
            mfc="white", mew=2, zorder=3)
    ax.axhline(d.returner.mean() * 100, color=MUTED, lw=1, ls="--", zorder=1)
    ax.annotate(f"overall {d.returner.mean()*100:.0f}%",
                xy=(10, d.returner.mean() * 100), xytext=(0, -15),
                textcoords="offset points", ha="right", color=MUTED, fontsize=9)
    ax.set_xticks(range(1, 11))
    ax.set_xlabel("Concentration of the first 90 days' plays "
                  "(1 = spread evenly, 10 = crammed into one fortnight)")
    ax.set_ylabel("Came back after a year (%)")
    ax.set_ylim(0, max(g.rate.max() * 130, 1))
    ax.grid(axis="y", color=GRID, lw=1); ax.set_axisbelow(True)

    # The title states what survived the control, not what the line looks like.
    if conf["survives_control"]:
        title = (f"Crammed into one fortnight predicts NOT coming back — and it "
                 f"holds with play count controlled ({conf['coef_alone']:+.2f} "
                 f"→ {conf['coef_controlled']:+.2f})")
    else:
        title = (f"The concentration effect is mostly play count: "
                 f"{conf['coef_alone']:+.2f} alone, {conf['coef_controlled']:+.2f} "
                 f"once volume is held constant")
    ax.set_title(title, color=INK, fontsize=11.5, loc="left", pad=12)
    _save(fig, "distinctiveness.svg")
    return g.round(4).to_dict("records")


def fig_shortlist(short: pd.DataFrame, simulated: bool = False):
    """
    The one figure that names things. A chart of track titles reads as real
    whatever the surrounding page says, and it is the figure most likely to be
    screenshotted away from its caveat -- so when the data is synthetic the
    figure carries that on its own face rather than relying on the prose.
    """
    n = min(15, len(short))
    d = short.head(n).iloc[::-1]

    if simulated:
        # Never print invented track titles. On real data these labels are real
        # recordings and naming them is the whole point; on simulated data they
        # are strings from a word list, and a bar chart makes any label look
        # like a finding. Rank plus sonic world says everything the figure is
        # actually entitled to say.
        labels = [f"#{n - i}" for i in range(n)]
    else:
        labels = [f"{r.name_}  ·  {r.artist}"[:46] if hasattr(r, "artist") else str(r.Index)
                  for r in d.rename(columns={"name": "name_"}).itertuples()]

    fig, ax = plt.subplots(figsize=(8.4, 0.34 * n + 1.2))
    bars = ax.barh(labels, d.memory_lane_index, color=BLUE, height=0.62)
    for b, v in zip(bars, d.memory_lane_index):
        ax.text(b.get_width() + 0.6, b.get_y() + b.get_height() / 2, f"{v:.0f}",
                va="center", color=INK, fontsize=9.5)
    ax.set_xlim(0, d.memory_lane_index.max() * 1.16)
    ax.set_xlabel("Memory Lane Index — modelled chance of coming back after a year (%)")
    ax.grid(axis="x", color=GRID, lw=1); ax.set_axisbelow(True)
    ax.tick_params(axis="y", labelsize=9)
    ax.set_title("The shortlist: recent tracks scored by a model fitted on "
                 "songs whose verdict is already in", color=INK, fontsize=12.5,
                 loc="left", pad=30 if simulated else 12)
    if simulated:
        ax.annotate("Simulated listener — bars are ranked positions, not real "
                    "recordings. Run it on a real account to get named tracks.",
                    xy=(0, 1.0), xycoords="axes fraction", xytext=(0, 12),
                    textcoords="offset points", ha="left", va="bottom",
                    color=MUTED, fontsize=10)
    _save(fig, "shortlist.svg")


# ── main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--birth-year", type=int, default=None,
                    help="needed to place your listening on the bump curve")
    args = ap.parse_args()

    FIGS.mkdir(parents=True, exist_ok=True)
    tracks, streams, source = load()

    birth_year = args.birth_year or source.get("birth_year")
    if not birth_year:
        sys.exit("Your birth year is needed to place listening on the "
                 "reminiscence-bump curve.\n  python memory-lane/run_memory_lane.py "
                 "--birth-year 1998")

    data_end = streams.played_at.max()
    lab = label_returners(streams, data_end)
    feat = encoding_features(streams, tracks, lab, birth_year)

    acoustic = acoustic_columns(feat)
    have_acoustic = len(acoustic) >= 4
    if have_acoustic:
        feat, worlds = cluster_worlds(feat, acoustic)
    else:
        feat["cluster"], feat["world"] = 0, "unclustered"
        worlds = {"k": 0, "note": "no acoustic features -- clustering skipped"}

    res = compare_models(feat, acoustic, have_acoustic)
    conf = confound_check(feat)
    scored = score_recent(feat, res, acoustic, have_acoustic)
    short, short_log = shortlist(scored)

    bump = fig_bump(feat)
    if have_acoustic:
        fig_worlds(feat, worlds)
    else:
        # Leaving a stale clustering figure next to metrics that say clustering
        # was skipped is worse than having no figure at all.
        (FIGS / "sonic_worlds.svg").unlink(missing_ok=True)
    fig_roc(res)
    conc = fig_distinctiveness(feat, conf)
    if len(short):
        fig_shortlist(short, simulated=bool(source.get("simulated")))

    OUT.mkdir(parents=True, exist_ok=True)
    cols = [c for c in ["track_id", "name", "artist", "memory_lane_index",
                        "world", "first_play", "enc_plays", "enc_concentration",
                        "enc_completion", "age_at_first_play", "bump_weight"]
            if c in short.columns]
    short_out = short[cols].copy()
    if "first_play" in short_out:
        short_out["first_play"] = short_out["first_play"].dt.date.astype(str)
    short_out.to_csv(OUT / "core_memory_tracks.csv", index=False)

    for k in ("_model", "_features", "_roc", "_roc_acoustic", "_train_frame"):
        res.pop(k, None)

    labelled = feat[feat.labelable]
    metrics = {
        "source": source,
        "definitions": {
            "returner": f"dormant >= {DORMANCY}d, then >= {RETURN_PLAYS} more plays",
            "encoding_window_days": ENCODING_WINDOW,
            "labelable_after_days": LABELABLE_AGE,
            "play_floor_ms": PLAY_FLOOR_MS,
            "note": "Returning after a year is not nostalgia. It is the "
                    "behaviour nostalgia leaves behind in a log, and unlike "
                    "nostalgia it can be held out and scored.",
        },
        "headline": {
            "tracks": int(len(feat)),
            "labelable": int(labelled.shape[0]),
            "too_new_to_label": int((~feat.labelable).sum()),
            "returner_rate": float(labelled.returner.mean()),
            "median_days_to_return": float(
                labelled.loc[labelled.returner == 1, "max_gap_days"].median()),
            "auc_behaviour": res["auc_behaviour"],
            "auc_with_acoustics": res.get("auc_behaviour_plus_acoustic"),
            "auc_delta": res.get("auc_delta"),
            "auc_delta_ci95": res.get("auc_delta_ci95"),
        },
        "reminiscence_bump": {
            **bump,
            "parameters": {"onset": psy.BUMP_ONSET, "offset": psy.BUMP_OFFSET,
                           "adult_floor": psy.ADULT_FLOOR},
            "caveat": ("Bump weight is near-constant within one year of one "
                       "person's listening, so it frames which era matters and "
                       "ranks nothing inside it. It is deliberately not part of "
                       "the per-track index."),
        },
        "sonic_worlds": worlds,
        "concentration_deciles": conc,
        "distinctiveness_confound": conf,
        "shortlist_selection": short_log,
        "model": res,
        "shortlist": short_out.round(4).to_dict("records") if len(short) else [],
        "blind_spots": [{"factor": a, "why": b} for a, b in psy.BLIND_SPOTS],
    }
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))

    print(json.dumps({k: metrics[k] for k in
                      ("definitions", "headline", "reminiscence_bump")},
                     indent=2, default=str))
    print(f"\nwritten: {OUT}/metrics.json, {OUT}/core_memory_tracks.csv, "
          f"{FIGS}/*.svg")
    if len(short):
        print(f"\nNext: python memory-lane/make_playlist.py   "
              f"(creates the playlist on your account; dry-run by default)")


if __name__ == "__main__":
    main()
