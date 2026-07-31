"""
Extract the CDNOW transaction log into data/cdnow_transactions.csv.

THE DATA
--------
CDNOW was an online music retailer (1994-2000, acquired by Bertelsmann). This
is its real transaction log: every purchase made by a 1/10th sample of the
customers who placed their FIRST order in the first quarter of 1997, followed
through 30 June 1998.

    23,570 customers · 69,659 transactions · Jan 1997 - Jun 1998

It is the dataset behind Fader, Hardie & Lee's work on customer-base analysis,
which is why it is a defensible thing to build on: the population is
well-documented and the cohort design is unusually clean.

WHY THE COHORT DESIGN MATTERS
-----------------------------
Every customer here was acquired inside one 3-month window and then observed
for at least 15 months. So a 180-day repeat-purchase window is fully observed
for every single customer -- nobody is scored as "did not return" merely for
having been acquired late. Most retention analyses have to make a judgment call
about censoring; this one does not, and that removes a whole class of error.

It ships inside the `lifetimes` package, so no download is required.

Usage:  python analysis/prepare_data.py
"""

from __future__ import annotations

import inspect
import os
from pathlib import Path

import pandas as pd

COLUMNS = ["customer_id", "date", "cds", "value"]


def locate_master() -> Path:
    import lifetimes.datasets as ds
    return Path(inspect.getfile(ds)).parent / "CDNOW_master.txt"


def main() -> None:
    src = locate_master()
    if not src.exists():
        raise SystemExit(f"CDNOW_master.txt not found at {src}. pip install lifetimes")

    # Whitespace-delimited, with a header row that is not a data row.
    df = pd.read_csv(src, sep=r"\s+", header=0, names=COLUMNS)
    df["date"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d")
    df = df.sort_values(["customer_id", "date"]).reset_index(drop=True)

    Path("data").mkdir(exist_ok=True)
    out = Path("data/cdnow_transactions.csv")
    df.to_csv(out, index=False)

    print(f"source       : {src}")
    print(f"transactions : {len(df):,}")
    print(f"customers    : {df['customer_id'].nunique():,}")
    print(f"date range   : {df['date'].min().date()} -> {df['date'].max().date()}")
    print(f"written      : {out} ({os.path.getsize(out)/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
