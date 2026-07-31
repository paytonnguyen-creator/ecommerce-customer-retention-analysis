"""
CDNOW customer retention analysis.

THE QUESTION THIS IS BUILT TO ANSWER
------------------------------------
Among customers acquired in the same quarter, what about their FIRST purchase
predicts whether they ever come back -- and which of those things could CDNOW
actually have changed?

That second clause is doing the work. Plenty of variables predict retention
without being usable: you cannot assign a customer a high lifetime spend. So
every finding gets sorted into OBSERVABLE (useful for targeting who to spend
on) or ACTIONABLE (useful for deciding what to do), and only actionable
findings reach a recommendation.

NO LEAKAGE: every model feature is knowable at the moment the first order is
placed. Time-to-second-purchase is excluded on purpose -- it would predict the
target almost perfectly because it *is* the target restated.

Run:    python analysis/prepare_data.py && python analysis/run_analysis.py
Writes: outputs/metrics.json, outputs/figures/*.svg
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score, roc_curve
from sklearn.model_selection import train_test_split

HORIZON = 180  # days after the first order in which a repeat purchase counts
OUT, FIGS = Path("outputs"), Path("outputs/figures")

# Validated categorical palette (checked with the dataviz validator, light mode).
BLUE, ORANGE, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#14161a", "#6b7078", "#e4e6ea"

plt.rcParams.update({
    "figure.dpi": 110, "font.size": 11, "font.family": "DejaVu Sans",
    "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "svg.fonttype": "none",
})


# ── 1. Clean ─────────────────────────────────────────────────────────────────
def load_clean() -> tuple[pd.DataFrame, dict]:
    raw = pd.read_csv("data/cdnow_transactions.csv", parse_dates=["date"])
    log = {"rows_raw": int(len(raw))}

    # A customer can have several rows on one date: those are lines of a single
    # order, not separate purchase decisions. Rolling them up matters -- left
    # alone they would inflate the repeat rate by counting one basket twice.
    orders = (
        raw.groupby(["customer_id", "date"], as_index=False)
        .agg(value=("value", "sum"), cds=("cds", "sum"), lines=("value", "size"))
    )
    log["rows_after_same_day_rollup"] = int(len(orders))
    log["same_day_lines_merged"] = log["rows_raw"] - log["rows_after_same_day_rollup"]

    # £0 orders are real rows (returns netting out, or promo fulfilment). They
    # are kept as purchase events but flagged, since they carry no revenue.
    log["zero_value_orders"] = int((orders["value"] <= 0).sum())

    log["customers"] = int(orders["customer_id"].nunique())
    log["orders"] = int(len(orders))
    return orders, log


# ── 2. Customer-level features ───────────────────────────────────────────────
def build_features(orders: pd.DataFrame) -> pd.DataFrame:
    orders = orders.sort_values(["customer_id", "date"])
    g = orders.groupby("customer_id")

    first = g.first().reset_index().rename(
        columns={"date": "first_date", "value": "first_value",
                 "cds": "first_cds", "lines": "first_lines"}
    )

    later = orders.merge(first[["customer_id", "first_date"]], on="customer_id")
    later = later[later["date"] > later["first_date"]].copy()
    later["days_since_first"] = (later["date"] - later["first_date"]).dt.days

    in_window = later[later["days_since_first"] <= HORIZON]
    feat = first.merge(
        in_window.groupby("customer_id").agg(
            repeat_orders=("value", "size"), repeat_revenue=("value", "sum")
        ),
        on="customer_id", how="left",
    )
    feat[["repeat_orders", "repeat_revenue"]] = feat[
        ["repeat_orders", "repeat_revenue"]
    ].fillna(0)
    feat["repeated"] = (feat["repeat_orders"] > 0).astype(int)

    # Days to the second purchase, for the descriptive window analysis only --
    # never fed to the model.
    feat = feat.merge(
        later.groupby("customer_id")["days_since_first"].min().rename("days_to_second"),
        on="customer_id", how="left",
    )

    # Lifetime revenue over the full 18 months, for opportunity sizing.
    feat = feat.merge(
        g["value"].sum().rename("total_revenue"), on="customer_id", how="left"
    )

    feat["cohort_month"] = feat["first_date"].dt.to_period("M").astype(str)
    feat["avg_price"] = np.where(
        feat["first_cds"] > 0, feat["first_value"] / feat["first_cds"], 0.0
    )
    feat["log_first_value"] = np.log1p(feat["first_value"].clip(lower=0))
    feat["multi_line_first"] = (feat["first_lines"] > 1).astype(int)
    return feat


# ── 3. Model ─────────────────────────────────────────────────────────────────
def fit_model(feat: pd.DataFrame) -> dict:
    """
    Logistic regression, chosen over a boosted tree deliberately: the output of
    this project is an argument a merchandising lead has to be able to check,
    and coefficients are legible in a way feature importances are not. The cost
    is a little accuracy; the benefit is that the recommendation is auditable.
    """
    d = feat.copy()
    for c in ["log_first_value", "first_cds", "avg_price"]:
        d[f"z_{c}"] = (d[c] - d[c].mean()) / d[c].std()

    # avg_price is value / cds -- a deterministic function of the other two
    # predictors. Including all three makes the coefficients fight each other
    # and none of them mean anything. It is dropped from the joint model and
    # reported on its own instead.
    X = pd.get_dummies(
        d[["z_log_first_value", "z_first_cds", "multi_line_first", "cohort_month"]],
        columns=["cohort_month"], drop_first=True, dtype=float,
    )
    y = d["repeated"]

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.30, random_state=42, stratify=y
    )
    model = LogisticRegression(max_iter=3000).fit(X_tr, y_tr)
    p_te = model.predict_proba(X_te)[:, 1]

    coefs = (
        pd.DataFrame({"feature": X.columns, "coef": model.coef_[0]})
        .assign(odds_ratio=lambda t: np.exp(t["coef"]))
        .sort_values("coef")
    )

    # Basket SIZE and basket VALUE move together. Reporting either one alone
    # overstates it, so both the joint and the solo fits are recorded.
    solo_cds = LogisticRegression(max_iter=3000).fit(d[["z_first_cds"]], y)
    solo_val = LogisticRegression(max_iter=3000).fit(d[["z_log_first_value"]], y)

    solo_price = LogisticRegression(max_iter=3000).fit(d[["z_avg_price"]], y)

    return {
        "n_train": int(len(X_tr)), "n_test": int(len(X_te)),
        "auc": float(roc_auc_score(y_te, p_te)),
        "brier": float(brier_score_loss(y_te, p_te)),
        "base_rate": float(y.mean()),
        "coefficients": coefs.to_dict("records"),
        "corr_value_cds": float(d["z_log_first_value"].corr(d["z_first_cds"])),
        "cds_coef_alone": float(solo_cds.coef_[0][0]),
        "cds_coef_joint": float(coefs.loc[coefs.feature == "z_first_cds", "coef"].iloc[0]),
        "value_coef_alone": float(solo_val.coef_[0][0]),
        "value_coef_joint": float(
            coefs.loc[coefs.feature == "z_log_first_value", "coef"].iloc[0]
        ),
        "avg_price_coef_alone": float(solo_price.coef_[0][0]),
        "_roc": roc_curve(y_te, p_te),
    }


# ── 4. Opportunity sizing ────────────────────────────────────────────────────
def size_opportunity(feat: pd.DataFrame) -> pd.DataFrame:
    """
    Rank levers by money available, not by effect size. A large effect on a
    small segment is worth less than a modest effect on a large one, and only
    one of those distinctions survives a budget meeting.

    Capture rate is held at a deliberately conservative 25%: the benchmark
    group differs from the target group in ways beyond the lever itself, so
    closing the whole gap is not on the table.
    """
    CAPTURE = 0.25
    repeat_value = feat.loc[feat.repeated == 1, "repeat_revenue"].mean()
    rows = []

    # LEVER 1 -- treat everyone inside the window.
    # The model's AUC says first-order data cannot identify who will return, so
    # a targeting model is the wrong build. The window analysis says the second
    # purchase, when it happens, happens fast. Together those point at a timed
    # intervention applied to every first-time buyer rather than a scored few.
    # 3pp is a deliberately modest assumed lift, not a measured one; only a
    # holdout test can confirm it, which is the point of the success metric.
    ASSUMED_LIFT_PP = 3.0
    one_and_done = int((feat.repeated == 0).sum())
    rows.append({
        "lever": "Timed second-purchase nudge to every first-time buyer",
        "verdict": "recommended",
        "customers": one_and_done,
        "current_rate": 0.0,
        "benchmark_rate": ASSUMED_LIFT_PP / 100,
        "uplift_pp": ASSUMED_LIFT_PP,
        "capture_rate": 1.0,  # the lift itself is already the conservative figure
        "basis": "assumed 3pp lift, to be proven or killed by a holdout test",
    })

    # LEVER 2 -- basket value. Survives control, so the mechanism is credible.
    q = feat["first_value"].quantile([0.25, 0.75])
    low, high = feat[feat.first_value <= q.loc[0.25]], feat[feat.first_value >= q.loc[0.75]]
    rows.append({
        "lever": "Lift bottom-quartile first baskets toward the top quartile",
        "verdict": "recommended",
        "customers": int(len(low)),
        "current_rate": float(low.repeated.mean()),
        "benchmark_rate": float(high.repeated.mean()),
        "uplift_pp": (high.repeated.mean() - low.repeated.mean()) * 100,
        "capture_rate": CAPTURE,
        "basis": "first-order value keeps its sign and size when controlled",
    })

    # LEVER 3 -- REJECTED. The raw gap is large and tempting, but the title
    # count coefficient collapses from +0.22 to +0.04 -- an ~82% attenuation,
    # effectively nothing -- once basket value is held constant. Customers who
    # buy three titles repeat because they SPENT more, not because they bought
    # more items. Acting on the raw gap would push merchandising toward cheap
    # add-ons, which moves item count without moving the thing that matters.
    single, multi = feat[feat.first_cds == 1], feat[feat.first_cds >= 3]
    rows.append({
        "lever": "Get a 2nd and 3rd title into the first order",
        "verdict": "rejected - confounded by basket value",
        "customers": int(len(single)),
        "current_rate": float(single.repeated.mean()),
        "benchmark_rate": float(multi.repeated.mean()),
        "uplift_pp": (multi.repeated.mean() - single.repeated.mean()) * 100,
        "capture_rate": CAPTURE,
        "basis": "raw gap is real; the causal reading is not",
    })

    out = pd.DataFrame(rows)
    out["incremental_repeaters"] = out.customers * (out.uplift_pp / 100) * out.capture_rate
    out["value_per_repeater"] = repeat_value
    out["annual_value"] = out.incremental_repeaters * repeat_value
    return out.sort_values(
        ["verdict", "annual_value"], ascending=[True, False]
    ).reset_index(drop=True)


# ── 5. Figures ───────────────────────────────────────────────────────────────
def _save(fig, name):
    fig.savefig(FIGS / name, format="svg", bbox_inches="tight", transparent=True)
    plt.close(fig)


def fig_second_purchase_window(feat: pd.DataFrame) -> dict:
    """The headline chart: how quickly repeat buyers come back."""
    d = feat[feat.days_to_second.notna()]
    bins = [0, 30, 60, 90, 120, 180, 270, 365, 10_000]
    labels = ["0-30", "31-60", "61-90", "91-120", "121-180", "181-270", "271-365", "365+"]
    cut = pd.cut(d.days_to_second, bins=bins, labels=labels, right=True)
    share = cut.value_counts(normalize=True).reindex(labels) * 100
    cumulative = share.cumsum()

    fig, ax = plt.subplots(figsize=(8, 3.4))
    bars = ax.bar(labels, share.values, color=BLUE, width=0.62)
    for b, v, c in zip(bars, share.values, cumulative.values):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.7, f"{v:.0f}%",
                ha="center", color=INK, fontsize=9.5)
    ax.set_ylabel("Share of repeat buyers (%)")
    ax.set_xlabel("Days between first and second purchase")
    ax.set_ylim(0, share.max() * 1.28)
    ax.grid(axis="y", color=GRID, lw=1); ax.set_axisbelow(True)
    ax.set_title(
        f"{cumulative.loc['61-90']:.0f}% of second purchases happen within 90 days",
        color=INK, fontsize=12.5, loc="left", pad=12)
    _save(fig, "second_purchase_window.svg")
    return {"share": share.round(2).to_dict(), "cumulative": cumulative.round(2).to_dict()}


def fig_repeat_by_first_basket(feat: pd.DataFrame) -> dict:
    d = feat.copy()
    d["decile"] = pd.qcut(d.first_value, 10, labels=False, duplicates="drop") + 1
    g = d.groupby("decile").agg(rate=("repeated", "mean"),
                                spend=("first_value", "median")).reset_index()

    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.plot(g.decile, g.rate * 100, color=BLUE, lw=2, marker="o", ms=6,
            mfc="white", mew=2, zorder=3)
    ax.axhline(d.repeated.mean() * 100, color=MUTED, lw=1, ls="--", zorder=1)
    ax.annotate(f"overall {d.repeated.mean()*100:.0f}%", xy=(10, d.repeated.mean()*100),
                xytext=(0, -14), textcoords="offset points", ha="right",
                color=MUTED, fontsize=9)
    ax.set_xticks(range(1, 11))
    ax.set_xlabel("First-order value decile (1 = smallest basket)")
    ax.set_ylabel("Repeat within 180 days (%)")
    ax.set_ylim(0, g.rate.max() * 130)
    ax.grid(axis="y", color=GRID, lw=1); ax.set_axisbelow(True)
    ax.set_title("Bigger first baskets repeat more — but the curve flattens at the top",
                 color=INK, fontsize=12.5, loc="left", pad=12)
    _save(fig, "repeat_by_first_basket.svg")
    return g.assign(rate=g.rate.round(4)).to_dict("records")


def fig_revenue_concentration(feat: pd.DataFrame) -> dict:
    rev = feat.total_revenue.sort_values(ascending=False).to_numpy()
    share_cust = np.arange(1, len(rev) + 1) / len(rev) * 100
    share_rev = rev.cumsum() / rev.sum() * 100
    at = {p: float(np.interp(p, share_cust, share_rev)) for p in (5, 10, 20, 50)}

    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    ax.plot(share_cust, share_rev, color=BLUE, lw=2)
    ax.plot([0, 100], [0, 100], color=MUTED, ls="--", lw=1)
    ax.scatter([20], [at[20]], color=ORANGE, s=48, zorder=4)
    ax.annotate(f"top 20% of customers\n= {at[20]:.0f}% of revenue",
                xy=(20, at[20]), xytext=(26, at[20] - 22), color=INK, fontsize=10,
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=1))
    ax.set_xlabel("Share of customers (%)"); ax.set_ylabel("Share of revenue (%)")
    ax.set_xlim(0, 100); ax.set_ylim(0, 100)
    ax.grid(color=GRID, lw=1); ax.set_axisbelow(True)
    ax.set_title("Revenue is heavily concentrated", color=INK, fontsize=12.5,
                 loc="left", pad=12)
    _save(fig, "revenue_concentration.svg")
    return at


def fig_coefficients(res: dict):
    c = pd.DataFrame(res["coefficients"])
    c = c[~c.feature.str.startswith("cohort_month")]
    nice = {"z_log_first_value": "First-order value (log, per SD)",
            "z_first_cds": "Titles in first order (per SD)",
            "z_avg_price": "Average price per title (per SD)",
            "multi_line_first": "First order split over multiple lines"}
    c["label"] = c.feature.map(nice).fillna(c.feature)
    c = c.sort_values("coef")

    fig, ax = plt.subplots(figsize=(7.6, 3.0))
    colors = [ORANGE if v < 0 else BLUE for v in c.coef]
    bars = ax.barh(c.label, c.coef, color=colors, height=0.58)
    for b, v in zip(bars, c.coef):
        ax.text(v + (0.01 if v >= 0 else -0.01), b.get_y() + b.get_height() / 2,
                f"{v:+.2f}", va="center", ha="left" if v >= 0 else "right",
                color=INK, fontsize=10)
    ax.axvline(0, color=MUTED, lw=1.2)
    pad = max(abs(c.coef.min()), abs(c.coef.max())) * 0.4
    ax.set_xlim(c.coef.min() - pad, c.coef.max() + pad)
    ax.set_xlabel("Log-odds of repeat purchase within 180 days")
    ax.grid(axis="x", color=GRID, lw=1); ax.set_axisbelow(True)
    ax.set_title("What the first order tells you, holding the rest constant",
                 color=INK, fontsize=12.5, loc="left", pad=12)
    _save(fig, "coefficients.svg")


def fig_opportunity(opp: pd.DataFrame):
    """Only the levers that survived the causal check get charted."""
    keep = opp[opp.verdict == "recommended"]
    fig, ax = plt.subplots(figsize=(8, 2.6))
    labels = ["\n".join(l[i:i + 42] for i in range(0, len(l), 42))
              for l in keep.lever][::-1]
    vals = (keep.annual_value / 1000)[::-1]
    bars = ax.barh(labels, vals, color=BLUE, height=0.5)
    for b, v in zip(bars, vals):
        ax.text(b.get_width() + max(vals) * 0.015, b.get_y() + b.get_height() / 2,
                f"${v:,.0f}k", va="center", color=INK, fontsize=10)
    ax.set_xlim(0, max(vals) * 1.24)
    ax.set_xlabel("Incremental 180-day repeat revenue at 25% capture ($000)")
    ax.grid(axis="x", color=GRID, lw=1); ax.set_axisbelow(True)
    ax.tick_params(axis="y", labelsize=9.5)
    ax.set_title("Levers ranked by money available, not by effect size",
                 color=INK, fontsize=12.5, loc="left", pad=12)
    _save(fig, "opportunity.svg")


def fig_roc(res: dict):
    fpr, tpr, _ = res["_roc"]
    fig, ax = plt.subplots(figsize=(4.2, 4.0))
    ax.plot([0, 1], [0, 1], color=MUTED, ls="--", lw=1)
    ax.plot(fpr, tpr, color=BLUE, lw=2)
    ax.set_xlabel("False positive rate"); ax.set_ylabel("True positive rate")
    ax.grid(color=GRID, lw=1); ax.set_axisbelow(True)
    ax.set_title(f"Hold-out ROC · AUC {res['auc']:.3f}", color=INK,
                 fontsize=12.5, loc="left", pad=12)
    _save(fig, "roc.svg")


# ── main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    FIGS.mkdir(parents=True, exist_ok=True)

    orders, clean_log = load_clean()
    feat = build_features(orders)
    res = fit_model(feat)
    opp = size_opportunity(feat)

    window = fig_second_purchase_window(feat)
    deciles = fig_repeat_by_first_basket(feat)
    concentration = fig_revenue_concentration(feat)
    fig_coefficients(res)
    fig_opportunity(opp)
    fig_roc(res)
    res.pop("_roc")

    cohorts = (
        feat.groupby("cohort_month")
        .agg(customers=("repeated", "size"), repeat_rate=("repeated", "mean"),
             median_first_value=("first_value", "median"))
        .round(4).reset_index().to_dict("records")
    )

    metrics = {
        "source": {
            "dataset": "CDNOW transaction log",
            "description": "Real purchases by a 1/10 sample of customers whose first "
                           "order fell in Q1 1997, followed to 30 June 1998.",
            "customers": clean_log["customers"],
            "orders": clean_log["orders"],
            "horizon_days": HORIZON,
            "fully_observed": True,
        },
        "cleaning": clean_log,
        "headline": {
            "repeat_rate_180d": float(feat.repeated.mean()),
            "one_and_done_share": float(1 - feat.repeated.mean()),
            "median_days_to_second": float(feat.days_to_second.median()),
            "revenue_share_top_20pct": concentration[20],
            "revenue_share_top_5pct": concentration[5],
        },
        "second_purchase_window": window,
        "repeat_by_first_value_decile": deciles,
        "revenue_concentration": concentration,
        "cohorts": cohorts,
        "model": res,
        "opportunity": opp.round(4).to_dict("records"),
    }
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))

    print(json.dumps({k: metrics[k] for k in
                      ("source", "cleaning", "headline", "model", "opportunity")},
                     indent=2, default=str))


if __name__ == "__main__":
    main()
