"""
The Pickleball Bottleneck -- analysis, forecast, and policy comparison.

THE QUESTION THIS IS BUILT TO ANSWER
------------------------------------
Open play rations a scarce court by making people stand in line. Two questions
follow, and only the second one is worth a product:

  1. When is it busy?  -- answerable, and largely uninteresting: it is busy
     after work, on weekends, and when the weather is nice.
  2. What does the busyness cost, who pays it, and can telling people in
     advance actually move any of it?

Everything here is sorted into two buckets, and the labels are load-bearing:

  RECOVERED  a pattern that was written into `simulate_courts.ASSUMPTIONS` and
             has now been read back out through a regression. It shows the
             pipeline works. It is not evidence about pickleball players.
  EMERGENT   a consequence of queueing that nobody wrote down: how convex the
             wait is in demand, how congestion hides itself by shedding
             players, how much of the wait a perfect forecast could remove,
             and which of three policies buys the most relief.

Only EMERGENT results are allowed to reach a recommendation.

Run:    python pickleball/analysis/run_analysis.py
Reads:  pickleball/data/{park_hours,scenarios,wait_histogram}.csv, assumptions.json
Writes: pickleball/outputs/metrics.json, pickleball/outputs/figures/*.svg
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "outputs"
FIGS = OUT / "figures"

TRAIN_YEARS, TEST_YEAR = (2012, 2013, 2014), 2015
PEAK_HOURS = (17, 18, 19)
MIN_ARRIVALS = 5      # below this the per-hour mean wait is too noisy to model
LOOKAHEAD_HOURS = 2   # the product's promise: how busy will it be in two hours

# Categorical slots 1-3 of the validated palette (all-pairs clean in light mode).
# Aqua sits below 3:1 on the light surface, so anything drawn in it is directly
# labelled -- the relief rule, not an optional nicety.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID, SURFACE = "#14161a", "#6b7078", "#e4e6ea", "#fcfcfb"

plt.rcParams.update({
    "figure.dpi": 110, "font.size": 11, "font.family": "DejaVu Sans",
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "svg.fonttype": "none",
    "svg.hashsalt": "pickleball-bottleneck",  # deterministic element ids
})


def save(fig, name: str, tight: bool = True) -> None:
    if tight:
        fig.tight_layout()
    # metadata Date=None strips the embedded creation timestamp; with the fixed
    # hashsalt above, identical inputs then give byte-identical SVGs.
    fig.savefig(FIGS / name, format="svg", bbox_inches="tight",
                metadata={"Date": None})
    plt.close(fig)


def wtd(values: pd.Series, weights: pd.Series) -> float:
    """Arrival-weighted mean. An unweighted mean of per-hour means would let a
    dead Tuesday morning cancel out a packed Thursday evening."""
    v, w = values.to_numpy(float), weights.to_numpy(float)
    ok = ~np.isnan(v) & (w > 0)
    return float(np.average(v[ok], weights=w[ok])) if ok.any() else float("nan")


# ── Load ─────────────────────────────────────────────────────────────────────
def load():
    ph = pd.read_csv(DATA / "park_hours.csv", parse_dates=["date"])
    ph["year"] = ph["date"].dt.year
    ph["month"] = ph["date"].dt.month
    # Minutes of playable light left when you turn up. Without this the
    # abandonment numbers are wrong: someone who arrives forty minutes before
    # an unlit court goes dark did not fail to get a game because it was busy.
    ph["mins_left"] = (ph.groupby(["park", "date"])["hour"].transform("max") + 1
                       - ph["hour"]) * 60
    sc = pd.read_csv(DATA / "scenarios.csv", parse_dates=["date"])
    hist = pd.read_csv(DATA / "wait_histogram.csv", index_col="hour")
    assumptions = json.loads((DATA / "assumptions.json").read_text())
    provenance = json.loads((DATA / "weather_provenance.json").read_text())
    return ph, sc, hist, assumptions, provenance


# ── 1. What the waiting actually costs (EMERGENT) ───────────────────────────
def cost_of_waiting(ph: pd.DataFrame, hist: pd.DataFrame) -> dict:
    total_wait, total_play = ph["sum_wait_min"].sum(), ph["sum_play_min"].sum()
    peak = ph[ph["hour"].isin(PEAK_HOURS)]
    peak_15 = peak[peak["year"] == TEST_YEAR]
    pw, pp = peak["sum_wait_min"].sum(), peak["sum_play_min"].sum()

    bins = np.array([int(c) for c in hist.columns])
    peak_hist = hist.loc[list(PEAK_HOURS)].sum(axis=0).to_numpy()
    share_over = lambda m: float(peak_hist[bins >= m].sum() / peak_hist.sum())

    # Two different reasons a person goes home without playing, and they demand
    # different products. Congestion is a queue you can route around; darkness
    # is a wall. Peak arrivals with at least 90 minutes of light left isolate
    # the first; the last playable hour isolates the second.
    roomy = peak[peak["mins_left"] >= 90]
    closing = ph[ph["mins_left"] <= 60]

    return {
        "player_visits": int(ph["arrivals"].sum()),
        "wait_share_all_hours": round(float(total_wait / (total_wait + total_play)), 4),
        "wait_share_peak": round(float(pw / (pw + pp)), 4),
        "peak_mean_wait_min": round(wtd(peak["mean_first_wait"], peak["arrivals"]), 2),
        "peak_p90_wait_min": round(wtd(peak["p90_first_wait"], peak["arrivals"]), 2),
        "peak_mean_wait_min_2015": round(wtd(peak_15["mean_first_wait"], peak_15["arrivals"]), 2),
        "peak_arrivals": int(peak["arrivals"].sum()),
        "peak_share_waiting_over_20min": round(share_over(20), 4),
        "peak_share_waiting_over_30min": round(share_over(30), 4),
        "peak_share_waiting_over_45min": round(share_over(45), 4),
        "mean_games_per_visit": round(float(ph["sum_games"].sum() / ph["arrivals"].sum()), 2),
        # abandonment, split by cause
        "peak_never_played_rate_all": round(wtd(peak["never_played_rate"], peak["arrivals"]), 4),
        "never_played_congestion_only": round(wtd(roomy["never_played_rate"], roomy["arrivals"]), 4),
        "never_played_last_hour_of_light": round(
            wtd(closing["never_played_rate"], closing["arrivals"]), 4),
        "arrivals_in_last_hour_of_light": int(closing["arrivals"].sum()),
        "share_of_all_arrivals_in_last_hour": round(
            float(closing["arrivals"].sum() / ph["arrivals"].sum()), 4),
    }


# ── 2. The bottleneck curve (EMERGENT) ──────────────────────────────────────
def bottleneck(ph: pd.DataFrame) -> dict:
    """Wait against demand.

    The shape is a U, and the left arm surprised me. An hour with three
    arrivals has a *longer* wait than an hour with fifteen, because pickleball
    needs four people to start anything: on an empty court you are not queueing
    for a court, you are queueing for opponents. Open play has a minimum viable
    crowd as well as a maximum one, and an app that simply steers people toward
    the quietest slot is giving bad advice at one end of its own range.

    Rows in the last 90 minutes of daylight are excluded here. They mix a
    different failure -- running out of light -- into the same curve, and it is
    measured separately in `cost_of_waiting`.
    """
    d = ph[(ph["arrivals"] >= 1) & (ph["mins_left"] >= 90)].copy()
    d["bin"] = pd.cut(d["arrivals"], bins=np.arange(0, 85, 5))
    grp = d.groupby("bin", observed=True).apply(
        lambda g: pd.Series({
            "arrivals": round(float(g["arrivals"].mean()), 2),
            "wait": round(wtd(g["mean_first_wait"], g["arrivals"]), 2),
            "never": round(wtd(g["never_played_rate"], g["arrivals"]), 4),
            "n": int(len(g)),
        }), include_groups=False,
    ).reset_index(drop=True)

    sweet = grp.loc[grp["wait"].idxmin()]
    lonely = grp.iloc[0]
    busiest = grp.loc[grp["arrivals"].idxmax()]

    # Steepness is measured on the congested arm only -- from the sweet spot
    # upward. Spanning the U would average the two arms against each other and
    # report a slope that exists nowhere on the curve.
    dem_ratio = busiest["arrivals"] / sweet["arrivals"]
    wait_ratio = busiest["wait"] / sweet["wait"]
    never_ratio = busiest["never"] / max(sweet["never"], 1e-6)

    return {
        "curve": grp.to_dict("records"),
        "sweet_spot_arrivals": sweet["arrivals"],
        "sweet_spot_wait_min": sweet["wait"],
        "wait_when_nearly_empty_min": lonely["wait"],
        "busiest_arrivals": busiest["arrivals"],
        "busiest_wait_min": busiest["wait"],
        "demand_ratio_busiest_vs_sweet": round(float(dem_ratio), 2),
        "wait_ratio_busiest_vs_sweet": round(float(wait_ratio), 2),
        "wait_convexity": round(float(wait_ratio / dem_ratio), 2),
        "abandonment_ratio_busiest_vs_sweet": round(float(never_ratio), 1),
        "abandonment_convexity": round(float(never_ratio / dem_ratio), 1),
    }


# ── 3. Forecasting the wait two hours out ───────────────────────────────────
FEATURES = ["hour", "dow", "month", "is_weekend", "temp_f", "precipitation", "wind",
            "is_wet", "t_index"]


def design(df: pd.DataFrame) -> pd.DataFrame:
    x = df[FEATURES].copy()
    x["is_weekend"] = x["is_weekend"].astype(int)
    x["is_wet"] = x["is_wet"].astype(int)
    for park in sorted(df["park"].unique())[1:]:  # drop-first one-hot
        x[f"park_{park}"] = (df["park"] == park).astype(int)
    # Cyclical hour: a linear model must not think 07:00 and 20:00 are far apart
    # in kind just because they are far apart in number.
    x["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    x["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    return x


def forecast(ph: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    d = ph.copy()
    d["t_index"] = (d["date"] - pd.Timestamp("2012-01-01")).dt.days
    # Train and score only where the hourly mean wait rests on enough people to
    # mean anything; predict everywhere, because the product has to answer for
    # quiet slots too -- those are the ones it will be recommending.
    train = d[d["year"].isin(TRAIN_YEARS) & (d["arrivals"] >= MIN_ARRIVALS)].copy()
    test = d[(d["year"] == TEST_YEAR) & (d["arrivals"] >= 1)].copy()
    score_mask = (test["arrivals"] >= MIN_ARRIVALS).to_numpy()

    y_tr, y_te = train["mean_first_wait"].to_numpy(), test["mean_first_wait"].to_numpy()
    X_tr, X_te = design(train), design(test)

    preds: dict[str, np.ndarray] = {}

    # (a) The naive baseline anyone can build without a model: the historical
    # average for this park, this hour, weekday-or-weekend.
    key = ["park", "hour", "is_weekend"]
    lookup = train.groupby(key)["mean_first_wait"].mean()
    preds["seasonal_mean"] = (
        test.set_index(key).index.map(lookup).to_numpy(float)
    )
    preds["seasonal_mean"] = np.where(
        np.isnan(preds["seasonal_mean"]), y_tr.mean(), preds["seasonal_mean"]
    )

    # (b) Ridge -- legible, and able to extrapolate the growth trend.
    ridge = Ridge(alpha=1.0).fit(
        (X_tr - X_tr.mean()) / X_tr.std().replace(0, 1), y_tr)
    preds["ridge"] = ridge.predict((X_te - X_tr.mean()) / X_tr.std().replace(0, 1))

    # (c) Gradient boosting -- more flexible, and structurally unable to
    # extrapolate: a tree can only ever predict values it saw in training, so a
    # rising trend runs straight into a ceiling on the far side of the split.
    hgb = HistGradientBoostingRegressor(random_state=0, max_iter=300,
                                        learning_rate=0.06).fit(X_tr, y_tr)
    preds["gbm"] = hgb.predict(X_te)

    # (d) The fix for (c): take the trend out, let the trees model the shape,
    # put the trend back. Same model class, one honest preprocessing step.
    trend = np.polyfit(train["t_index"], y_tr, 1)
    resid = y_tr - np.polyval(trend, train["t_index"])
    hgb_d = HistGradientBoostingRegressor(random_state=0, max_iter=300,
                                          learning_rate=0.06).fit(
        X_tr.drop(columns=["t_index"]), resid)
    preds["gbm_detrended"] = (hgb_d.predict(X_te.drop(columns=["t_index"]))
                              + np.polyval(trend, test["t_index"]))

    # (e) The oracle: hand the model the true expected demand that generated
    # the arrivals. It cannot be beaten by any amount of feature engineering,
    # so whatever error it still carries is the queue's own randomness -- the
    # noise floor the product has to be designed around.
    orc_tr = pd.DataFrame({"lam": train["lam"], "hour": train["hour"]})
    orc_te = pd.DataFrame({"lam": test["lam"], "hour": test["hour"]})
    for park in sorted(d["park"].unique())[1:]:
        orc_tr[f"park_{park}"] = (train["park"] == park).astype(int).to_numpy()
        orc_te[f"park_{park}"] = (test["park"] == park).astype(int).to_numpy()
    orc = HistGradientBoostingRegressor(random_state=0, max_iter=300,
                                        learning_rate=0.06).fit(orc_tr, y_tr)
    preds["oracle_true_demand"] = orc.predict(orc_te)

    ys, = np.where(score_mask)
    scores = {
        name: {"mae": round(float(mean_absolute_error(y_te[ys], p[ys])), 3),
               "rmse": round(float(np.sqrt(np.mean((y_te[ys] - p[ys]) ** 2))), 3),
               "r2": round(float(r2_score(y_te[ys], p[ys])), 3),
               "mean_bias": round(float(np.mean(p[ys] - y_te[ys])), 3)}
        for name, p in preds.items()
    }

    # SELECTION RULE, stated before the numbers were looked at: minimum absolute
    # bias among models within MAE_BUDGET of the best MAE.
    #
    # Not lowest MAE. This product tells someone how long they will wait, and
    # the two ways of being wrong do not cost the same. Quote 20 minutes to
    # someone who waits 10 and they are pleased. Quote 10 to someone who waits
    # 20 and they stop opening the app. A model that is systematically low is
    # therefore worse than a model that is noisier but centred -- and the
    # untreated boosted tree is systematically low, because trees cannot
    # extrapolate a growth trend past the edge of their training data.
    MAE_BUDGET = 1.25
    deployable = {n: s for n, s in scores.items() if n != "oracle_true_demand"}
    best_mae = min(s["mae"] for s in deployable.values())
    shortlist = [n for n, s in deployable.items() if s["mae"] <= best_mae * MAE_BUDGET]
    best = min(shortlist, key=lambda n: abs(deployable[n]["mean_bias"]))

    floor, reachable = scores["oracle_true_demand"]["mae"], scores[best]["mae"]
    naive = scores["seasonal_mean"]["mae"]

    out = {
        "train_rows": int(len(train)), "test_rows": int(len(test)),
        "scored_rows": int(score_mask.sum()),
        "test_mean_wait_min": round(float(y_te[ys].mean()), 2),
        "train_mean_wait_min": round(float(y_tr.mean()), 2),
        "scores": scores,
        "selection_rule": (f"lowest |bias| among models within {MAE_BUDGET:.2f}x of the "
                           f"best MAE; under-promising costs trust asymmetrically"),
        "lowest_mae_model": min(deployable, key=lambda n: deployable[n]["mae"]),
        "best_deployable_model": best,
        "noise_floor_mae": floor,
        "share_of_gap_to_floor_closed": round(
            float((naive - reachable) / (naive - floor)), 3) if naive > floor else None,
        "ridge_coefficients": {
            c: round(float(v), 3)
            for c, v in sorted(zip(X_tr.columns, ridge.coef_),
                               key=lambda kv: -abs(kv[1]))
        },
    }
    test = test.assign(**{f"pred_{k}": v for k, v in preds.items()})
    return out, test


# ── 4. What the advice is worth (EMERGENT) ──────────────────────────────────
def advice_value(test: pd.DataFrame, model: str) -> dict:
    """A player intends to arrive at a peak hour. The app offers the quietest
    slot within +/- LOOKAHEAD_HOURS. How much waiting does taking it avoid?

    This is the *private* return -- one player moving does not change the queue.
    The system-level return, where everybody moves at once, is the
    shift_15pct_off_peak scenario, and it is a different and much smaller number.
    """
    idx = test.set_index(["park", "date", "hour"]).sort_index()
    have = set(idx.index)
    wait = idx["mean_first_wait"].to_dict()
    never = idx["never_played_rate"].to_dict()
    left = idx["mins_left"].to_dict()
    pred = idx[f"pred_{model}"].to_dict()

    rows = []
    for park, date, hour in idx.index:
        if hour not in PEAK_HOURS:
            continue
        cand = [h for h in range(hour - LOOKAHEAD_HOURS, hour + LOOKAHEAD_HOURS + 1)
                if (park, date, h) in have]
        if len(cand) < 2:
            continue
        k = lambda h: (park, date, h)
        p = np.array([pred[k(h)] for h in cand])
        model_h = cand[int(np.argmin(p))]
        # Same choice, but refusing any slot without an hour and a half of light
        # left -- the cheapest possible guardrail, and the data says it matters.
        lit = [h for h in cand if left[k(h)] >= 90] or cand
        guarded_h = lit[int(np.argmin([pred[k(h)] for h in lit]))]
        perfect_h = cand[int(np.argmin([wait[k(h)] for h in cand]))]
        rows.append({
            "naive_wait": wait[k(hour)], "model_wait": wait[k(model_h)],
            "guarded_wait": wait[k(guarded_h)], "perfect_wait": wait[k(perfect_h)],
            "naive_never": never[k(hour)], "model_never": never[k(model_h)],
            "guarded_never": never[k(guarded_h)],
        })

    r = pd.DataFrame(rows)
    naive_m, inf_m, per_m = r["naive_wait"].mean(), r["model_wait"].mean(), r["perfect_wait"].mean()
    return {
        "decisions_evaluated": int(len(r)),
        "wait_if_you_just_turn_up_min": round(float(naive_m), 2),
        "wait_following_model_advice_min": round(float(inf_m), 2),
        "wait_following_perfect_advice_min": round(float(per_m), 2),
        "minutes_saved_by_model": round(float(naive_m - inf_m), 2),
        "minutes_saved_by_perfect": round(float(naive_m - per_m), 2),
        "share_of_available_saving_captured": round(float((naive_m - inf_m) / (naive_m - per_m)), 3)
        if naive_m > per_m else None,
        "pct_reduction_in_wait": round(float(100 * (naive_m - inf_m) / naive_m), 1),
        # Chasing the shortest queue can walk someone straight into the dark.
        # If this rises, minimising wait is the wrong objective on its own.
        "never_played_if_you_just_turn_up": round(float(r["naive_never"].mean()), 4),
        "never_played_following_model_advice": round(float(r["model_never"].mean()), 4),
        "never_played_with_daylight_guardrail": round(float(r["guarded_never"].mean()), 4),
        "wait_with_daylight_guardrail_min": round(float(r["guarded_wait"].mean()), 2),
    }


# ── 5. Policy comparison (EMERGENT) ─────────────────────────────────────────
POLICY_LABELS = {
    "baseline": "Today: 8 courts, all four off",
    "two_more_courts": "Build 2 more courts (+25%)",
    "winners_stay": "Winners stay on",
    "shift_15pct_off_peak": "App shifts 15% off peak",
}
# Cost is a judgement, not a computation -- nothing in a court log says what a
# programme costs. It is recorded per lever so a reader can disagree with the
# estimate instead of with the arithmetic.
POLICY_EFFORT = {
    "two_more_courts": "High -- capital budget, land, 12-18 months",
    "winners_stay": "None -- it is a sign on the fence and a word from the ambassador",
    "shift_15pct_off_peak": "Medium -- build and market an app, then earn 15% adoption",
}


def policies(sc: pd.DataFrame) -> dict:
    peak = sc[sc["hour"].isin(PEAK_HOURS)]
    rows = {}
    for name, g in peak.groupby("scenario"):
        w, p = g["sum_wait_min"].sum(), g["sum_play_min"].sum()
        rows[name] = {
            "label": POLICY_LABELS.get(name, name),
            "peak_mean_wait_min": round(wtd(g["mean_first_wait"], g["arrivals"]), 2),
            "peak_never_played_rate": round(wtd(g["never_played_rate"], g["arrivals"]), 4),
            "wait_share_of_court_time": round(float(w / (w + p)), 4),
            "effort": POLICY_EFFORT.get(name, "n/a -- this is the status quo"),
        }
    base = rows["baseline"]["peak_mean_wait_min"]
    for name, r in rows.items():
        r["minutes_vs_today"] = round(r["peak_mean_wait_min"] - base, 2)
        r["pct_vs_today"] = round(100 * (r["peak_mean_wait_min"] - base) / base, 1)

    # The free lever measured against the expensive one.
    capex = base - rows["two_more_courts"]["peak_mean_wait_min"]
    rule = rows["winners_stay"]["peak_mean_wait_min"] - base
    return {
        "scenarios": rows,
        "capex_saving_min": round(capex, 2),
        "rotation_rule_saving_min": round(rule, 2),
        "rule_change_as_share_of_capex": round(rule / capex, 3) if capex else None,
    }


# ── Figures ─────────────────────────────────────────────────────────────────
def fig_demand(ph: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    for label, mask, colour in [("Weekday", ~ph["is_weekend"], BLUE),
                                ("Weekend", ph["is_weekend"], ORANGE)]:
        s = ph[mask].groupby("hour")["arrivals"].mean()
        ax.plot(s.index, s.values, lw=2, color=colour, label=label)
        ax.annotate(label, (s.index[-1], s.values[-1]), xytext=(6, 0),
                    textcoords="offset points", color=colour, fontsize=10, va="center")
    ax.set_xlabel("Hour of day")
    ax.set_ylabel("Mean arrivals per court-hour")
    ax.set_title("When people show up", color=INK, fontsize=12.5, loc="left", pad=12)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.set_xlim(6.5, 21.6)
    ax.text(0, -0.30, "RECOVERED — this is the arrival model read back out, not a measurement.",
            transform=ax.transAxes, fontsize=9, color=MUTED)
    save(fig, "demand_by_hour.svg")


def fig_temperature(ph: pd.DataFrame) -> None:
    d = ph.copy()
    d["bin"] = pd.cut(d["temp_f"], bins=np.arange(25, 100, 5))
    s = d[~d["is_wet"]].groupby("bin", observed=True)["arrivals"].mean()
    centres = np.array([b.mid for b in s.index])

    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    ax.axvspan(65, 75, color=ORANGE, alpha=0.10, lw=0)
    ax.plot(centres, s.values, lw=2, color=BLUE, marker="o", ms=5,
            markerfacecolor=SURFACE, markeredgewidth=1.6, markeredgecolor=BLUE)
    ax.set_xlabel("Temperature (°F), dry hours only")
    ax.set_ylabel("Mean arrivals per court-hour")
    ax.set_title("Demand against temperature", color=INK, fontsize=12.5, loc="left", pad=12)
    ax.annotate("65–75°F", (70, ax.get_ylim()[1] * 0.06), ha="center",
                color=ORANGE, fontsize=10)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.text(0, -0.30, "RECOVERED — the peak is where the simulator was told to put it.",
            transform=ax.transAxes, fontsize=9, color=MUTED)
    save(fig, "temperature_response.svg")


def fig_bottleneck(res: dict) -> None:
    g = pd.DataFrame(res["curve"])

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.4, 5.8), sharex=True,
                                 gridspec_kw={"height_ratios": [1.3, 1]})
    a1.plot(g["arrivals"], g["wait"], lw=2, color=BLUE)
    a1.set_ylabel("Mean wait for a\nfirst game (min)")
    a1.set_title("Too few players is its own kind of wait",
                 color=INK, fontsize=12.5, loc="left", pad=12)
    a1.grid(axis="y", color=GRID, lw=0.8); a1.set_axisbelow(True)

    sx, sy = res["sweet_spot_arrivals"], res["sweet_spot_wait_min"]
    a1.plot([sx], [sy], marker="o", ms=8, color=BLUE,
            markerfacecolor=SURFACE, markeredgewidth=2)
    a1.annotate(f"sweet spot\n{sx:.0f} arrivals, {sy:.1f} min",
                (sx, sy), xytext=(18, 40), textcoords="offset points",
                fontsize=9.5, color=MUTED)
    a1.annotate("nobody to play with", (g["arrivals"].iloc[0], g["wait"].iloc[0]),
                xytext=(10, -6), textcoords="offset points", fontsize=9.5, color=MUTED)
    a1.annotate("nowhere to play", (g["arrivals"].iloc[-1], g["wait"].iloc[-1]),
                xytext=(-12, 6), textcoords="offset points", ha="right",
                fontsize=9.5, color=MUTED)

    a2.plot(g["arrivals"], 100 * g["never"], lw=2, color=ORANGE)
    a2.set_ylabel("Arrivals who never\nget a game (%)")
    a2.set_xlabel("Arrivals in the hour")
    a2.grid(axis="y", color=GRID, lw=0.8); a2.set_axisbelow(True)
    a2.text(0.98, 0.86,
            f"{res['demand_ratio_busiest_vs_sweet']}× the demand → "
            f"{res['wait_ratio_busiest_vs_sweet']}× the wait, "
            f"but {res['abandonment_ratio_busiest_vs_sweet']:.0f}× the walk-aways",
            transform=a2.transAxes, ha="right", fontsize=9.5, color=MUTED)
    a2.text(0, -0.34,
            "EMERGENT — nothing in the arrival model specifies either curve. "
            "Last 90 minutes of daylight excluded.",
            transform=a2.transAxes, fontsize=9, color=MUTED)
    save(fig, "bottleneck_curve.svg")


def fig_wait_share(ph: pd.DataFrame) -> None:
    g = ph.groupby("hour")[["sum_wait_min", "sum_play_min"]].sum()
    g = g[g.sum(axis=1) > 0]
    total = g.sum(axis=1)
    play, wait = 100 * g["sum_play_min"] / total, 100 * g["sum_wait_min"] / total

    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    ax.bar(g.index, play, color=BLUE, width=0.78, label="Playing")
    ax.bar(g.index, wait, bottom=play + 0.6, color=ORANGE, width=0.78, label="Waiting")
    ax.set_ylabel("Share of time at the park (%)")
    ax.set_xlabel("Hour of day")
    ax.set_ylim(0, 101)
    ax.set_title("What an hour at the park is actually spent on",
                 color=INK, fontsize=12.5, loc="left", pad=34)
    ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0), ncols=2,
              fontsize=10)
    ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
    ax.text(0, -0.30, "EMERGENT — a consequence of eight courts and a first-in-first-out rack.",
            transform=ax.transAxes, fontsize=9, color=MUTED)
    save(fig, "waiting_vs_playing.svg")


def fig_forecast(fc: dict) -> None:
    order = ["seasonal_mean", "ridge", "gbm", "gbm_detrended", "oracle_true_demand"]
    names = {"seasonal_mean": "Historical average\n(park × hour × weekend)",
             "ridge": "Ridge regression", "gbm": "Gradient boosting",
             "gbm_detrended": "Gradient boosting,\ntrend removed",
             "oracle_true_demand": "Oracle: knows true demand"}
    maes = [fc["scores"][k]["mae"] for k in order]
    chosen = fc["best_deployable_model"]
    colours = [ORANGE if k == chosen else BLUE for k in order[:4]] + [AQUA]

    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    bars = ax.barh([names[k] for k in order], maes, color=colours, height=0.62)
    for bar, m, k in zip(bars, maes, order):
        tag = "  ← shipped" if k == chosen else ""
        ax.annotate(f"{m:.2f} min{tag}", (bar.get_width(), bar.get_y() + bar.get_height() / 2),
                    xytext=(6, 0), textcoords="offset points", va="center",
                    fontsize=10, color=INK)
    ax.axvline(fc["noise_floor_mae"], color=AQUA, lw=1.4, ls=(0, (4, 3)))
    ax.invert_yaxis()
    ax.set_xlabel("Mean absolute error on the 2015 hold-out (minutes)")
    ax.set_xlim(0, max(maes) * 1.22)
    ax.set_title("No model can beat the queue's own randomness",
                 color=INK, fontsize=12.5, loc="left", pad=12)
    ax.grid(axis="x", color=GRID, lw=0.8); ax.set_axisbelow(True)
    ax.text(0, -0.28,
            "EMERGENT — the oracle is handed the true demand, so its remaining error "
            "is irreducible.",
            transform=ax.transAxes, fontsize=9, color=MUTED)
    save(fig, "forecast_accuracy.svg")


def fig_policies(pol: dict) -> None:
    order = ["winners_stay", "baseline", "shift_15pct_off_peak", "two_more_courts"]
    rows = pol["scenarios"]
    vals = [rows[k]["peak_mean_wait_min"] for k in order]
    labels = [rows[k]["label"] for k in order]
    colours = [ORANGE if k == "winners_stay" else BLUE for k in order]

    fig, ax = plt.subplots(figsize=(7.4, 3.9))
    bars = ax.barh(labels, vals, color=colours, height=0.62)
    for bar, k in zip(bars, order):
        delta = rows[k]["minutes_vs_today"]
        tag = "today" if k == "baseline" else f"{delta:+.1f} min"
        ax.annotate(f"{rows[k]['peak_mean_wait_min']:.1f}   ({tag})",
                    (bar.get_width(), bar.get_y() + bar.get_height() / 2),
                    xytext=(6, 0), textcoords="offset points", va="center",
                    fontsize=10, color=INK)
    ax.invert_yaxis()
    ax.set_xlabel("Mean wait for a first game, 17:00–19:59 (minutes)")
    ax.set_xlim(0, max(vals) * 1.42)
    ax.set_title("Three levers, one of which is free", color=INK, fontsize=12.5,
                 loc="left", pad=12)
    ax.grid(axis="x", color=GRID, lw=0.8); ax.set_axisbelow(True)
    ax.text(0, -0.32, "EMERGENT — identical arrivals and game lengths in every scenario.",
            transform=ax.transAxes, fontsize=9, color=MUTED)
    save(fig, "policy_comparison.svg")


def fig_advice(av: dict) -> None:
    labels = ["Turn up when you meant to", "Follow the model's slot",
              "…plus a daylight guardrail", "Perfect hindsight"]
    waits = [av["wait_if_you_just_turn_up_min"], av["wait_following_model_advice_min"],
             av["wait_with_daylight_guardrail_min"], av["wait_following_perfect_advice_min"]]
    nevers = [100 * av["never_played_if_you_just_turn_up"],
              100 * av["never_played_following_model_advice"],
              100 * av["never_played_with_daylight_guardrail"], float("nan")]
    # Status quo in orange, everything else in blue: this is a magnitude
    # comparison of one measure, so hue carries "the thing being improved on",
    # not four separate identities.
    colours = [ORANGE, BLUE, BLUE, BLUE]

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.4, 3.7), sharey=True,
                                 gridspec_kw={"wspace": 0.08})
    for ax, vals, xlab, title, unit in [
        (a1, waits, "Mean wait for a first game (min)", "Waiting", " min"),
        (a2, nevers, "Arrivals who never get a game (%)", "Going home with nothing", "%"),
    ]:
        shown = [v for v in vals if not np.isnan(v)]
        bars = ax.barh(labels, [0 if np.isnan(v) else v for v in vals],
                       color=colours, height=0.62)
        for bar, v in zip(bars, vals):
            if np.isnan(v):
                ax.annotate("n/a", (0, bar.get_y() + bar.get_height() / 2),
                            xytext=(6, 0), textcoords="offset points", va="center",
                            fontsize=10, color=MUTED)
                continue
            ax.annotate(f"{v:.1f}{unit}", (bar.get_width(), bar.get_y() + bar.get_height() / 2),
                        xytext=(6, 0), textcoords="offset points", va="center",
                        fontsize=10.5, color=INK)
        ax.set_xlabel(xlab)
        ax.set_xlim(0, max(shown) * 1.32)
        ax.set_title(title, color=INK, fontsize=11.5, loc="left", pad=8)
        ax.grid(axis="x", color=GRID, lw=0.8); ax.set_axisbelow(True)
    a1.invert_yaxis()

    fig.suptitle("The advice is worth more for the games you get than the minutes you save",
                 color=INK, fontsize=12.5, x=0.005, ha="left", y=1.04)
    a1.text(0, -0.40,
            "EMERGENT — private return to one player; the system-level return, when "
            "everyone moves at once, is far smaller.",
            transform=a1.transAxes, fontsize=9, color=MUTED)
    save(fig, "advice_value.svg", tight=False)


def fig_daylight(ph: pd.DataFrame, cost: dict) -> None:
    """The one hard constraint in this project that is neither assumed nor
    emergent -- it is astronomy, computed from Seattle's latitude."""
    # nunique, not count: every playable hour appears once per park, and five
    # parks share one sky.
    by_month = ph.groupby(ph["date"].dt.month).apply(
        lambda g: g.groupby("date")["hour"].nunique().mean(), include_groups=False)

    d = ph[ph["arrivals"] > 0].copy()
    d["bucket"] = pd.cut(d["mins_left"], [0, 60, 120, 180, 240, 900],
                         labels=["<1h", "1–2h", "2–3h", "3–4h", "4h+"])
    g = d.groupby("bucket", observed=True).apply(
        lambda x: 100 * wtd(x["never_played_rate"], x["arrivals"]), include_groups=False)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.4, 3.9))
    a1.plot(by_month.index, by_month.values, lw=2, color=BLUE, marker="o", ms=5,
            markerfacecolor=SURFACE, markeredgewidth=1.6, markeredgecolor=BLUE)
    a1.set_xlabel("Month")
    a1.set_ylabel("Playable hours per day")
    a1.set_title("Unlit courts have a season", color=INK, fontsize=11.5, loc="left", pad=8)
    a1.set_xticks(range(1, 13))
    a1.set_xticklabels(list("JFMAMJJASOND"))
    a1.grid(axis="y", color=GRID, lw=0.8); a1.set_axisbelow(True)

    bars = a2.bar(g.index.astype(str), g.values,
                  color=[ORANGE] + [BLUE] * (len(g) - 1), width=0.62)
    for bar, v in zip(bars, g.values):
        a2.annotate(f"{v:.0f}%", (bar.get_x() + bar.get_width() / 2, v),
                    xytext=(0, 5), textcoords="offset points", ha="center",
                    fontsize=10.5, color=INK)
    a2.set_xlabel("Playable light left when you arrive")
    a2.set_ylabel("Never get a game (%)")
    a2.set_title("And arriving late is worse than arriving busy",
                 color=INK, fontsize=11.5, loc="left", pad=8)
    a2.set_ylim(0, max(g.values) * 1.25)
    a2.grid(axis="y", color=GRID, lw=0.8); a2.set_axisbelow(True)

    a1.text(0, -0.30,
            f"Sunrise/sunset from solar geometry at 47.61°N. "
            f"{100 * cost['share_of_all_arrivals_in_last_hour']:.0f}% of all arrivals "
            f"land in that first bucket.",
            transform=a1.transAxes, fontsize=9, color=MUTED)
    save(fig, "daylight_cliff.svg")


# ── Main ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    FIGS.mkdir(parents=True, exist_ok=True)
    ph, sc, hist, assumptions, provenance = load()

    cost = cost_of_waiting(ph, hist)
    neck = bottleneck(ph)
    fc, test = forecast(ph)
    av = advice_value(test, fc["best_deployable_model"])
    fc["advice_model"] = fc["best_deployable_model"]
    pol = policies(sc)

    fig_demand(ph)
    fig_temperature(ph)
    fig_bottleneck(neck)
    fig_wait_share(ph)
    fig_forecast(fc)
    fig_policies(pol)
    fig_advice(av)
    fig_daylight(ph, cost)

    metrics = {
        "weather_provenance": provenance,
        "declared_assumptions": assumptions["assumptions"],
        "cost_of_waiting": cost,
        "bottleneck": neck,
        "forecast": fc,
        "advice_value": av,
        "policies": pol,
        "config": {"train_years": list(TRAIN_YEARS), "test_year": TEST_YEAR,
                   "peak_hours": list(PEAK_HOURS), "min_arrivals_for_model": MIN_ARRIVALS,
                   "lookahead_hours": LOOKAHEAD_HOURS},
    }
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")

    print(json.dumps({k: v for k, v in metrics.items()
                      if k in ("cost_of_waiting", "advice_value")}, indent=2))
    print("\nforecast MAE:", {k: v["mae"] for k, v in fc["scores"].items()})
    print("policies:", {k: v["peak_mean_wait_min"] for k, v in pol["scenarios"].items()})
    print(f"\nwrote {OUT / 'metrics.json'} and {len(list(FIGS.glob('*.svg')))} figures")
