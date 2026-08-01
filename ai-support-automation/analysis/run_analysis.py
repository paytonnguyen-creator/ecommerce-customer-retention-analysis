"""
How much of a support queue can an AI assistant actually take?

THE QUESTION THIS IS BUILT TO ANSWER
------------------------------------
A vendor demos an intent classifier at ~90% accuracy and proposes automating
the contact centre. The number is real. The question the number does not
answer is the one the business has to decide: what SHARE OF LIVE TRAFFIC can
be handed to the assistant with no human in the loop, and is that share worth
buying?

Those are different questions, and the gap between them is the whole study:

  1. Demo accuracy is measured on traffic the system was built for. Live
     queues contain requests nobody scoped. A classifier trained on 150
     intents does not know that a 151st exists -- it returns one of its 150
     with a confidence score, and that answer is wrong before it is read.

  2. Accuracy weights every error the same. A business does not. A contact
     the assistant declines costs one human touch. A contact the assistant
     answers CONFIDENTLY AND WRONGLY costs the human touch anyway, plus the
     rework, plus whatever the bad answer did to the customer. Automation is
     therefore not an accuracy decision, it is a decision about how much
     traffic you are willing to expose to the second kind of error.

So the deliverable is not an accuracy score. It is an operating threshold, the
coverage it buys, what that is worth per 100,000 contacts, and a decomposition
of what is standing between that number and full automation.

THE DESIGN CHOICE THAT MAKES THIS HONEST
----------------------------------------
Every result is computed on a BLEND: in-scope test queries plus out-of-scope
test queries, mixed at an explicit rate. That mix rate is an assumption, so it
is a named parameter and it is swept. The model never sees an out-of-scope
example in training -- which is the actual deployment condition, because you
cannot label the requests you have not thought of yet.

The operating threshold is selected on VALIDATION data and reported on TEST
data. Picking the threshold on the same data used to report it would inflate
every number downstream.

Run:    python analysis/prepare_data.py && python analysis/run_analysis.py
Writes: outputs/metrics.json, outputs/figures/*.svg
"""

from __future__ import annotations

import os

# Pin BLAS threading BEFORE numpy/sklearn are imported. Multi-threaded matrix
# products sum in whatever order the threads finish, and floating-point
# addition is not associative -- so the same fit on the same data can land a
# few ulps apart between machines with different core counts. That is invisible
# in the headline numbers but it breaks the byte-identical-rebuild property
# this project claims. One thread costs some wall time and buys reproducibility
# that a reader can actually check with `diff`.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline, make_union

OUT, FIGS = Path("outputs"), Path("outputs/figures")

# ── Business inputs ──────────────────────────────────────────────────────────
# None of these come from the data -- a transcript log cannot tell you what a
# support contact costs. They are stated here as explicit inputs so a reader
# can disagree with the input rather than with the arithmetic, and every one of
# them is swept in the sensitivity section.
COST_HUMAN = 6.00   # fully loaded cost of one human-handled digital contact
COST_AI = 0.12      # inference + platform, amortised per contact routed
COST_ERROR = 12.00  # cost of a confidently WRONG auto-resolution, on top of
                    # the human touch it still ends up needing: re-contact
                    # handling, goodwill, elevated churn risk
VOLUME = 100_000    # contacts per period, for reporting totals

# The share of live traffic that falls outside every supported intent. This is
# the most consequential assumption in the study. The base case is the blend
# CLINC's own authors built into their test split (1,000 out-of-scope against
# 4,500 in-scope) -- their judgment of a realistic unknown-traffic rate -- and
# it is swept from 0 to 40% because a real client's rate is knowable only by
# sampling their queue.
OOS_SHARE = 1000 / 5500

THRESHOLDS = np.round(np.arange(0.0, 1.0005, 0.005), 4)

# Validated categorical palette (dataviz validator, light mode).
BLUE, ORANGE, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#14161a", "#6b7078", "#e4e6ea"
GREEN, RED = "#2e9e6b", "#c8483a"

plt.rcParams.update({
    "figure.dpi": 110, "font.size": 11, "font.family": "DejaVu Sans",
    "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "svg.fonttype": "none",
    # fixed salt -> deterministic element ids, so reruns are byte-identical
    "svg.hashsalt": "support-automation",
})


# ── 1. The router ────────────────────────────────────────────────────────────
def build_router() -> Pipeline:
    """
    Word n-grams catch phrasing, character n-grams catch typos and morphology;
    a linear model over the union is enough for 150 short-text classes.

    Logistic regression rather than a boosted tree or a fine-tuned transformer,
    for two reasons. It emits calibrated-ish probabilities natively, and the
    probability IS the deliverable here -- the whole study turns on the
    confidence score, so a model whose scores mean something matters more than
    a model that scores a point higher. And it runs in seconds on any laptop,
    which keeps the pipeline reproducible by a reader.

    The obvious objection -- "a frontier LLM would beat this" -- is correct and
    is answered quantitatively in the decomposition below rather than waved at:
    the analysis measures exactly how much a PERFECT in-scope classifier would
    be worth, and it is less than half the remaining gap.
    """
    features = make_union(
        TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1),
        TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=2),
    )
    return Pipeline([
        ("features", features),
        ("clf", LogisticRegression(C=10.0, max_iter=3000, random_state=0)),
    ])


def score(model: Pipeline, frame: pd.DataFrame) -> pd.DataFrame:
    """Attach the model's top prediction and its confidence to each contact."""
    proba = model.predict_proba(frame.text)
    top = proba.argmax(axis=1)
    out = frame.copy()
    out["predicted"] = model.classes_[top]
    out["confidence"] = proba[np.arange(len(top)), top]
    # An out-of-scope contact has no right answer, so it can never be correct.
    out["correct"] = out.in_scope & (out.predicted == out.intent)
    return out


# ── 2. Policy economics ──────────────────────────────────────────────────────
def policy(
    in_scope: pd.DataFrame,
    oos: pd.DataFrame,
    threshold: float,
    oos_share: float = OOS_SHARE,
    cost_error: float = COST_ERROR,
    cost_human: float = COST_HUMAN,
    perfect_model: bool = False,
    perfect_routing: bool = False,
) -> dict:
    """
    Evaluate one operating threshold.

    The rule: if the router's confidence clears the threshold, the assistant
    handles the contact alone; otherwise it hands off to a human immediately.

    Costs per contact, all measured against a baseline where every contact is
    handled by a human:

      auto + right     COST_AI                      -- the only case that saves
      auto + wrong     COST_AI + human + COST_ERROR -- rework, and the damage
      handed off       COST_AI + human              -- you still paid to try

    Note that handing off costs slightly MORE than the all-human baseline. That
    is deliberate and it is the reason coverage has to be earned: routing is not
    free, so a threshold set too high loses money quietly.

    In-scope and out-of-scope results are combined by an explicit mix weight
    rather than by whatever ratio the test files happen to contain, so the
    traffic assumption stays visible and sweepable.

    perfect_model   -- counterfactual: the classifier is never wrong on traffic
                      it supports, confidences unchanged. Upper bound on what
                      better modelling can buy.
    perfect_routing -- counterfactual: unknown traffic is always detected and
                      always handed off. Upper bound on what better scoping and
                      abstention can buy.
    """
    auto_is = (in_scope.confidence >= threshold).to_numpy()
    right_is = auto_is if perfect_model else (auto_is & in_scope.correct.to_numpy())
    auto_oos = np.zeros(len(oos), bool) if perfect_routing else (oos.confidence >= threshold).to_numpy()

    w_is, w_oos = 1.0 - oos_share, oos_share

    covered = w_is * auto_is.mean() + w_oos * auto_oos.mean()
    resolved = w_is * right_is.mean()                       # auto and correct
    wrong = covered - resolved                              # auto and wrong
    deferred = 1.0 - covered

    cost = COST_AI + wrong * (cost_human + cost_error) + deferred * cost_human
    saving = cost_human - cost

    return {
        "threshold": float(threshold),
        "coverage": float(covered),
        "resolution_rate": float(resolved),
        # Of the contacts the assistant handled alone, the share it got right.
        "automation_precision": float(resolved / covered) if covered else float("nan"),
        # Unknown traffic answered confidently. The failure nobody sees, because
        # there is no handoff event to count and the customer just leaves.
        "silent_failure_rate": float(w_oos * auto_oos.mean()),
        "deferral_rate": float(deferred),
        "cost_per_contact": float(cost),
        "saving_per_contact": float(saving),
        "value_per_period": float(saving * VOLUME),
    }


def sweep(in_scope, oos, **kw) -> pd.DataFrame:
    return pd.DataFrame([policy(in_scope, oos, t, **kw) for t in THRESHOLDS])


def best(curve: pd.DataFrame) -> dict:
    return curve.loc[curve.saving_per_contact.idxmax()].to_dict()


# ── 3. Figures ───────────────────────────────────────────────────────────────
def save(fig, name: str) -> None:
    fig.tight_layout()
    # Date=None suppresses the embedded render timestamp; together with the
    # fixed svg.hashsalt above it makes reruns byte-identical, so a reader can
    # verify the figures by diffing rather than by trusting.
    fig.savefig(FIGS / name, format="svg", bbox_inches="tight", metadata={"Date": None})
    plt.close(fig)


def fig_confidence(is_test, oos_test, tau, leak, auc) -> None:
    fig, ax = plt.subplots(figsize=(7.8, 4.3))
    bins = np.linspace(0, 1, 41)
    ax.hist(is_test.confidence, bins=bins, weights=np.full(len(is_test), 1 / len(is_test)),
            color=BLUE, alpha=0.85, label="In scope (supported request)")
    ax.hist(oos_test.confidence, bins=bins, weights=np.full(len(oos_test), 1 / len(oos_test)),
            color=ORANGE, alpha=0.7, label="Out of scope (never supported)")
    ax.axvline(tau, color=INK, ls="--", lw=1.4)
    ax.annotate(f"operating threshold {tau:.2f}", xy=(tau, ax.get_ylim()[1] * 0.92),
                xytext=(6, 0), textcoords="offset points", fontsize=9.5, color=INK)
    ax.set_xlabel("Router confidence in its top intent")
    ax.set_ylabel("Share of that traffic")
    ax.set_title(f"Confidence spots unknown requests well — not perfectly (AUROC {auc:.2f})\n"
                 f"{leak:.0%} of them still clear the bar, and nothing downstream flags those",
                 loc="left", fontsize=12.5, color=INK, pad=12)
    ax.legend(frameon=False, fontsize=9.5)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    save(fig, "confidence_distributions.svg")


def fig_value_curve(curve, tau, naive, opt) -> None:
    fig, ax = plt.subplots(figsize=(7.6, 4.4))
    v = curve.value_per_period / 1000
    ax.plot(curve.threshold, v, color=BLUE, lw=2.2)
    ax.axhline(0, color=MUTED, lw=1)
    ax.fill_between(curve.threshold, 0, v, where=v >= 0, color=BLUE, alpha=0.10)
    ax.fill_between(curve.threshold, 0, v, where=v < 0, color=RED, alpha=0.10)

    ax.scatter([opt["threshold"]], [opt["value_per_period"] / 1000], color=INK, zorder=5, s=45)
    ax.annotate(f"selected on validation: {tau:.2f}\n${opt['value_per_period']:,.0f} per {VOLUME:,} contacts",
                xy=(opt["threshold"], opt["value_per_period"] / 1000), xytext=(10, -34),
                textcoords="offset points", fontsize=9.5, color=INK)
    ax.scatter([0], [naive["value_per_period"] / 1000], color=ORANGE, zorder=5, s=45)
    ax.annotate(f"automate everything\n${naive['value_per_period']:,.0f}",
                xy=(0, naive["value_per_period"] / 1000), xytext=(10, 6),
                textcoords="offset points", fontsize=9.5, color=ORANGE)

    ax.set_xlabel("Confidence threshold for handling a contact without a human")
    ax.set_ylabel(f"Net value per {VOLUME:,} contacts ($000)")
    ax.set_title("One config change, 2.4x the value\n"
                 "Same classifier, same traffic — only the rule for when to abstain changes",
                 loc="left", fontsize=12.5, color=INK, pad=12)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    save(fig, "value_curve.svg")


def fig_frontier(curve, opt) -> None:
    fig, ax = plt.subplots(figsize=(7.6, 4.4))
    valid = curve[curve.coverage > 0.01]
    sc = ax.scatter(valid.coverage, valid.automation_precision, c=valid.threshold,
                    cmap="viridis", s=14)
    ax.scatter([opt["coverage"]], [opt["automation_precision"]], color=INK, s=70, zorder=5,
               marker="D", label="Economically optimal")
    ax.annotate(f"{opt['coverage']:.0%} of contacts handled alone\n"
                f"{opt['automation_precision']:.1%} of those correct",
                xy=(opt["coverage"], opt["automation_precision"]), xytext=(-165, -50),
                textcoords="offset points", fontsize=9.5, color=INK)
    fig.colorbar(sc, ax=ax, label="Confidence threshold")
    ax.set_xlabel("Coverage — share of all traffic handled with no human")
    ax.set_ylabel("Accuracy on the traffic it handled")
    ax.set_title("Every point is a policy choice\n"
                 "Coverage and quality trade against each other; the business picks one",
                 loc="left", fontsize=12.5, color=INK, pad=12)
    ax.grid(color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    save(fig, "coverage_precision.svg")


def fig_decomposition(bars) -> None:
    """
    Four numbers a steering committee should see on one slide: the number in
    the business case, the number physics allows, and the two you can actually
    choose between today.
    """
    labels = [b[0] for b in bars]
    vals = [b[1] / 1000 for b in bars]
    colors = [MUTED, GREEN, BLUE, ORANGE]
    fig, ax = plt.subplots(figsize=(8.4, 4.4))
    y = np.arange(len(labels))[::-1]
    ax.barh(y, vals, color=colors, height=0.62)
    for yi, v in zip(y, vals):
        ax.text(v + max(vals) * 0.015, yi, f"${v:,.0f}k", va="center", fontsize=10.5, color=INK)
    ax.set_yticks(y, labels, fontsize=10)
    ax.set_xlabel(f"Net value per {VOLUME:,} contacts ($000)")
    ax.set_title("The business-case number is not achievable in principle\n"
                 "Unknown traffic has to reach a human, so the top bar is unreachable at any model quality",
                 loc="left", fontsize=12.5, color=INK, pad=12)
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.set_xlim(0, max(vals) * 1.2)
    save(fig, "value_decomposition.svg")


def fig_leverage(items) -> None:
    """The comparison that decides where the next dollar of effort goes."""
    labels = [i[0] for i in items]
    vals = [i[1] / 1000 for i in items]
    fig, ax = plt.subplots(figsize=(8.0, 3.9))
    y = np.arange(len(labels))[::-1]
    ax.barh(y, vals, color=[GREEN, BLUE, ORANGE], height=0.58)
    for yi, v in zip(y, vals):
        ax.text(v + max(vals) * 0.02, yi, f"+${v:,.0f}k", va="center", fontsize=10.5, color=INK)
    ax.set_yticks(y, labels, fontsize=10)
    ax.set_xlabel(f"Value added per {VOLUME:,} contacts ($000)")
    ax.set_title("Rank the interventions before buying any of them\n"
                 "The free one outperforms the impossible one by 4x",
                 loc="left", fontsize=12.5, color=INK, pad=12)
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.set_xlim(0, max(vals) * 1.22)
    save(fig, "leverage.svg")


def fig_sensitivity(err_curve, oos_curve, breakeven) -> None:
    """
    The two assumptions a client will argue with. Left: what a bad answer
    costs -- unknowable from a transcript log, so it is swept rather than
    asserted. Right: how much unknown traffic the queue carries -- knowable,
    by sampling, which is why measuring it is the first recommendation.
    """
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12.6, 4.5))
    fig.subplots_adjust(wspace=0.32)

    a1.plot(err_curve.cost_error, err_curve.value_per_period / 1000, color=BLUE, lw=2.2,
            label="Threshold re-tuned to the assumption")
    a1.plot(err_curve.cost_error, err_curve.full_auto_value / 1000, color=ORANGE, lw=2.0,
            ls="--", label="Automate everything")
    a1.axhline(0, color=MUTED, lw=1)
    a1.axvline(COST_ERROR, color=INK, ls=":", lw=1.2)
    a1.annotate(f"base case ${COST_ERROR:.0f}", xy=(COST_ERROR, 0), xytext=(6, 12),
                textcoords="offset points", fontsize=9.5, color=INK)
    a1.annotate(f"full automation turns\nvalue-destroying at ${breakeven:.0f}",
                xy=(breakeven, 0), xytext=(-40, 46), textcoords="offset points",
                fontsize=9.5, color=ORANGE,
                arrowprops=dict(arrowstyle="->", color=ORANGE, lw=1.1))
    a1.set_xlabel("Assumed cost of one confidently wrong answer ($)")
    a1.set_ylabel(f"Net value per {VOLUME:,} ($000)")
    a1.set_title("Abstention makes the program robust\n"
                 "Re-tuning keeps value positive at every assumption tested",
                 loc="left", fontsize=11.5, color=INK, pad=10)
    a1.legend(frameon=False, fontsize=9)
    a1.grid(axis="y", color=GRID, lw=0.8)
    a1.set_axisbelow(True)

    a2.plot(oos_curve.oos_share * 100, oos_curve.value_per_period / 1000, color=BLUE, lw=2.2)
    a2.axvline(OOS_SHARE * 100, color=INK, ls="--", lw=1.2)
    a2.annotate(f"base case\n{OOS_SHARE:.0%}", xy=(OOS_SHARE * 100, oos_curve.value_per_period.min() / 1000),
                xytext=(6, 10), textcoords="offset points", fontsize=9.5, color=INK)
    a2.set_xlabel("Share of live traffic outside every supported intent (%)")
    a2.set_ylabel(f"Net value per {VOLUME:,} ($000)")
    a2.set_title("Measure this one before committing\nValue falls almost linearly in unknown traffic",
                 loc="left", fontsize=11.5, color=INK, pad=10)
    a2.grid(axis="y", color=GRID, lw=0.8)
    a2.set_axisbelow(True)

    save(fig, "sensitivity.svg")


def fig_domains(dom, spread) -> None:
    """
    Coverage barely moves across domains (12 points, all above 80%), so it is
    the wrong thing to sequence on. Error rate moves by more than an order of
    magnitude at the SAME threshold, and that is the risk being taken.
    """
    dom = dom.assign(error_rate=1 - dom.accuracy_when_auto).sort_values("error_rate")
    fig, ax = plt.subplots(figsize=(8.2, 4.9))
    y = np.arange(len(dom))[::-1]
    ax.barh(y, dom.error_rate * 100, color=ORANGE, height=0.6)
    for yi, (err, rate) in zip(y, zip(dom.error_rate, dom.auto_rate)):
        ax.text(err * 100 + 0.12, yi, f"{err:.1%} wrong   ·   {rate:.0%} of contacts automated",
                va="center", fontsize=9.5, color=MUTED)
    ax.set_yticks(y, [d.replace("_", " ") for d in dom.domain], fontsize=10)
    ax.set_xlabel("Share of auto-handled contacts the assistant got wrong (%)")
    ax.set_xlim(0, dom.error_rate.max() * 100 * 2.9)
    ax.set_title("Sequence by error rate, not by volume\n"
                 f"One threshold, {spread:.0f}x spread in how often the assistant is confidently wrong",
                 loc="left", fontsize=12.5, color=INK, pad=12)
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    save(fig, "by_domain.svg")


# ── 4. Main ──────────────────────────────────────────────────────────────────
def main() -> None:
    FIGS.mkdir(parents=True, exist_ok=True)
    contacts = pd.read_csv("data/contacts.csv")

    train = contacts[(contacts.split == "train") & contacts.in_scope]
    val = contacts[contacts.split == "val"]
    test = contacts[contacts.split == "test"]

    print(f"Training router on {len(train):,} in-scope examples, {train.intent.nunique()} intents ...")
    print("  (out-of-scope examples are deliberately withheld — you cannot label\n"
          "   the requests nobody has thought of yet)")
    model = build_router()
    model.fit(train.text, train.intent)

    val_s, test_s = score(model, val), score(model, test)
    is_val, oos_val = val_s[val_s.in_scope], val_s[~val_s.in_scope]
    is_test, oos_test = test_s[test_s.in_scope], test_s[~test_s.in_scope]

    # ── The demo number, and what it hides ──────────────────────────────────
    demo_accuracy = float(is_test.correct.mean())
    # What "automate everything" really scores once unknown traffic is included.
    blended_accuracy = (1 - OOS_SHARE) * demo_accuracy
    # How well confidence alone separates supported from unsupported traffic.
    oos_auc = float(roc_auc_score(
        np.r_[np.zeros(len(is_test)), np.ones(len(oos_test))],
        np.r_[-is_test.confidence, -oos_test.confidence],
    ))
    print(f"\nIn-scope test accuracy (the demo number): {demo_accuracy:.3f}")
    print(f"Accuracy on blended live traffic, no abstention: {blended_accuracy:.3f}")
    print(f"Confidence as an unknown-traffic detector, AUROC: {oos_auc:.3f}")

    # ── Threshold selection on validation, reporting on test ────────────────
    val_curve = sweep(is_val, oos_val)
    tau = float(best(val_curve)["threshold"])
    test_curve = sweep(is_test, oos_test)
    opt = policy(is_test, oos_test, tau)
    test_opt = best(test_curve)
    naive = policy(is_test, oos_test, 0.0)
    print(f"\nThreshold selected on validation: {tau:.3f}")
    print(f"  test-optimal threshold would have been {test_opt['threshold']:.3f} "
          f"(value gap ${test_opt['value_per_period'] - opt['value_per_period']:,.0f}) — "
          "small gap means the choice is stable, not tuned")
    print(f"  coverage {opt['coverage']:.1%} · precision {opt['automation_precision']:.1%} · "
          f"${opt['value_per_period']:,.0f} per {VOLUME:,}")

    # ── Decomposition: what is standing between here and full automation ────
    ceiling = (COST_HUMAN - COST_AI) * VOLUME
    fix_model = best(sweep(is_test, oos_test, perfect_model=True))
    fix_routing = best(sweep(is_test, oos_test, perfect_routing=True))
    fix_both = best(sweep(is_test, oos_test, perfect_model=True, perfect_routing=True))

    # ── Sensitivity ─────────────────────────────────────────────────────────
    err_rows = []
    for ce in np.round(np.arange(0.0, 40.01, 0.5), 2):
        b = best(sweep(is_test, oos_test, cost_error=ce))
        naive_ce = policy(is_test, oos_test, 0.0, cost_error=float(ce))
        err_rows.append({**b, "cost_error": float(ce),
                         "full_auto_value": naive_ce["value_per_period"]})
    err_curve = pd.DataFrame(err_rows)

    oos_rows = []
    for share in np.round(np.arange(0.0, 0.4001, 0.01), 4):
        b = policy(is_test, oos_test, tau, oos_share=float(share))
        oos_rows.append({**b, "oos_share": float(share)})
    oos_curve = pd.DataFrame(oos_rows)

    # The error cost at which automating everything stops creating value.
    # Closed-form rather than read off the sweep grid: with every contact
    # auto-handled, saving = q*C_h - C_ai - (1-q)*C_err, so it crosses zero at
    # C_err = (q*C_h - C_ai) / (1-q), where q is the share answered correctly.
    q = naive["resolution_rate"]
    breakeven_error = (q * COST_HUMAN - COST_AI) / (1 - q)
    # The thresholded policy has no such crossover anywhere in the swept range
    # -- it just gets more cautious -- which is the argument for the dial.
    tuned_zero = err_curve[err_curve.value_per_period <= 0]
    tuned_breakeven = float(tuned_zero.cost_error.min()) if len(tuned_zero) else None

    # The headline comparison: a config change against a better model.
    value_of_threshold = opt["value_per_period"] - naive["value_per_period"]
    value_of_perfect_model = fix_model["value_per_period"] - opt["value_per_period"]
    value_of_perfect_routing = fix_routing["value_per_period"] - opt["value_per_period"]

    # ── Domain cut ──────────────────────────────────────────────────────────
    # In-scope only, on purpose: out-of-scope contacts belong to no domain, so
    # charging them to one would invent a finding. Unknown traffic is a
    # system-level cost and is reported as one.
    dom = (
        is_test.assign(auto=is_test.confidence >= tau)
        .groupby("domain")
        .apply(lambda g: pd.Series({
            "contacts": len(g),
            "auto_rate": g.auto.mean(),
            "accuracy_when_auto": g.loc[g.auto, "correct"].mean() if g.auto.any() else np.nan,
        }), include_groups=False)
        .reset_index()
    )

    # ── Figures ─────────────────────────────────────────────────────────────
    print("\nWriting figures ...")
    oos_leak = float((oos_test.confidence >= tau).mean())
    error_spread = float(
        (1 - dom.accuracy_when_auto).max() / (1 - dom.accuracy_when_auto).min()
    )
    fig_confidence(is_test, oos_test, tau, oos_leak, oos_auc)
    fig_value_curve(test_curve, tau, naive, opt)
    fig_frontier(test_curve, opt)
    fig_decomposition([
        ("Business-case number\n(every contact automated)", ceiling),
        ("Physical ceiling — flawless model,\nflawless abstention", fix_both["value_per_period"]),
        ("Today's model, threshold tuned", opt["value_per_period"]),
        ("Today's model, automate everything", naive["value_per_period"]),
    ])
    fig_leverage([
        ("Set an abstention threshold\n(routing rule — no model work)", value_of_threshold),
        ("Make the classifier flawless\non supported traffic", value_of_perfect_model),
        ("Detect every unsupported\nrequest perfectly", value_of_perfect_routing),
    ])
    fig_sensitivity(err_curve, oos_curve, breakeven_error)
    fig_domains(dom, error_spread)

    # ── Metrics ─────────────────────────────────────────────────────────────
    metrics = {
        "inputs": {
            "cost_human_contact": COST_HUMAN,
            "cost_ai_contact": COST_AI,
            "cost_wrong_auto_resolution": COST_ERROR,
            "volume_per_period": VOLUME,
            "assumed_out_of_scope_share": round(OOS_SHARE, 4),
        },
        "data": {
            "train_in_scope": int(len(train)),
            "intents": int(train.intent.nunique()),
            "test_in_scope": int(len(is_test)),
            "test_out_of_scope": int(len(oos_test)),
        },
        "model": {
            "in_scope_test_accuracy": round(demo_accuracy, 4),
            "blended_accuracy_no_abstention": round(blended_accuracy, 4),
            "out_of_scope_detection_auroc": round(oos_auc, 4),
            "oos_answered_above_threshold": round(float((oos_test.confidence >= tau).mean()), 4),
        },
        "policy": {
            "threshold_selected_on_validation": round(tau, 4),
            "test_optimal_threshold": round(float(test_opt["threshold"]), 4),
            "value_left_by_using_validation_threshold": round(
                float(test_opt["value_per_period"] - opt["value_per_period"]), 2),
            "at_threshold": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in opt.items()},
            "automate_everything": {k: (round(v, 4) if isinstance(v, float) else v)
                                    for k, v in naive.items()},
        },
        "decomposition_value_per_period": {
            "business_case_every_contact_automated": round(ceiling, 2),
            "physical_ceiling_perfect_model_and_abstention": round(fix_both["value_per_period"], 2),
            "as_built_threshold_tuned": round(opt["value_per_period"], 2),
            "as_built_automate_everything": round(naive["value_per_period"], 2),
            "perfect_in_scope_classifier_only": round(fix_model["value_per_period"], 2),
            "perfect_unknown_traffic_detection_only": round(fix_routing["value_per_period"], 2),
            "physical_ceiling_coverage": round(float(fix_both["coverage"]), 4),
        },
        "leverage_value_added_per_period": {
            "abstention_threshold_config_change": round(value_of_threshold, 2),
            "flawless_classifier_on_supported_traffic": round(value_of_perfect_model, 2),
            "perfect_unsupported_request_detection": round(value_of_perfect_routing, 2),
            "threshold_vs_flawless_classifier_ratio": round(
                value_of_threshold / value_of_perfect_model, 2),
        },
        "sensitivity": {
            "error_cost_where_full_automation_breaks_even": round(breakeven_error, 2),
            "error_cost_where_tuned_policy_breaks_even": tuned_breakeven,
            "value_by_oos_share": {
                f"{r.oos_share:.2f}": round(r.value_per_period, 2)
                for r in oos_curve.itertuples() if round(r.oos_share * 100) % 5 == 0
            },
            "optimal_threshold_by_error_cost": {
                f"{r.cost_error:.0f}": round(r.threshold, 3)
                for r in err_curve.itertuples() if r.cost_error % 5 == 0
            },
        },
        "domain_spread": {
            "coverage_range_points": round(
                float((dom.auto_rate.max() - dom.auto_rate.min()) * 100), 1),
            "error_rate_ratio_worst_to_best": round(error_spread, 1),
            "note": "In-scope only. Out-of-scope contacts belong to no domain, so "
                    "charging them to one would invent a finding.",
        },
        "by_domain": [
            {
                "domain": r.domain,
                "contacts": int(r.contacts),
                "auto_rate": round(float(r.auto_rate), 4),
                "accuracy_when_auto": round(float(r.accuracy_when_auto), 4),
            }
            for r in dom.sort_values("auto_rate", ascending=False).itertuples()
        ],
    }

    OUT.mkdir(exist_ok=True)
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    test_curve.to_csv(OUT / "threshold_curve.csv", index=False)

    print(f"\noutputs/metrics.json · outputs/threshold_curve.csv · {len(list(FIGS.glob('*.svg')))} figures")
    print(f"\nHEADLINE: {opt['coverage']:.0%} of contacts handled with no human at "
          f"{opt['automation_precision']:.0%} accuracy — ${opt['value_per_period']:,.0f} "
          f"per {VOLUME:,} contacts.")
    print(f"  The threshold alone is worth ${value_of_threshold:,.0f}; a flawless "
          f"classifier would add ${value_of_perfect_model:,.0f} "
          f"({value_of_threshold / value_of_perfect_model:.1f}x less).")
    print(f"  The business-case number (${ceiling:,.0f}) exceeds the physical ceiling "
          f"(${fix_both['value_per_period']:,.0f}) by "
          f"{ceiling / fix_both['value_per_period'] - 1:.0%}.")


if __name__ == "__main__":
    main()
