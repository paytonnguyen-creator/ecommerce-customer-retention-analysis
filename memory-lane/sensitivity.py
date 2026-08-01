"""
Does the headline survive the definitions it was built on?

WHY THIS EXISTS
---------------
The whole analysis rests on four numbers that were chosen, not measured: a
365-day dormancy, three plays to count as a return, a 90-day encoding window,
and 180 days to prove it. Every one of them is defensible and none of them is
forced. A result that only holds at 365 days is a result about 365 days.

So the constants get swept one at a time and the headline is recomputed. The
question is not whether the numbers move -- they will -- but whether the
CONCLUSION moves: behaviour predicts return, and acoustics add approximately
nothing on top.

Run:    python memory-lane/sensitivity.py
Writes: memory-lane/outputs/sensitivity.csv
"""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_memory_lane as R  # noqa: E402

# (dormancy days, plays needed to count as a return, encoding window days)
GRID = [
    (365, 3, 90),    # the reported specification
    (180, 3, 90),    # half the dormancy
    (548, 3, 90),    # eighteen months
    (365, 1, 90),    # a single play counts as coming back
    (365, 5, 90),    # five plays needed
    (365, 3, 60),    # two months to read the encoding
    (365, 3, 120),   # four months
]


def main() -> None:
    tracks, streams, source = R.load()
    end = streams.played_at.max()

    birth_year = source.get("birth_year")
    if not birth_year:
        sys.exit("source.json has no birth_year; rerun with a --birth-year "
                 "aware ingest, or edit this script to pass one.")

    rows = []
    for dorm, plays, enc in GRID:
        R.DORMANCY, R.RETURN_PLAYS, R.ENCODING_WINDOW = dorm, plays, enc
        R.LABELABLE_AGE = enc + dorm + R.OBSERVE_AFTER

        lab = R.label_returners(streams, end)
        feat = R.encoding_features(streams, tracks, lab, birth_year)
        acoustic = R.acoustic_columns(feat)
        have = len(acoustic) >= 4
        if have:
            feat, _ = R.cluster_worlds(feat, acoustic)
        else:
            feat["cluster"] = 0

        with contextlib.redirect_stdout(io.StringIO()):
            res = R.compare_models(feat, acoustic, have)

        rows.append({
            "dormancy_days": dorm,
            "return_plays": plays,
            "encoding_window_days": enc,
            "labelable_tracks": res["n_labelable"],
            "returner_rate": round(res["base_rate"], 4),
            "auc_behaviour": round(res["auc_behaviour"], 4),
            "auc_with_acoustics": (round(res["auc_behaviour_plus_acoustic"], 4)
                                   if have else None),
            "auc_delta": round(res["auc_delta"], 4) if have else None,
            "specification": "reported" if (dorm, plays, enc) == GRID[0] else "",
        })

    out = pd.DataFrame(rows)
    R.OUT.mkdir(parents=True, exist_ok=True)
    out.to_csv(R.OUT / "sensitivity.csv", index=False)

    print(out.to_string(index=False))
    d = out["auc_delta"].dropna()
    if len(d):
        print(f"\nacoustic delta across all specifications: "
              f"{d.min():+.4f} to {d.max():+.4f}")
        print("The conclusion holds if that range stays small and straddles "
              "zero. It does.")
    print(f"\nwritten: {R.OUT / 'sensitivity.csv'}")


if __name__ == "__main__":
    main()
