"""
Build the contact log this case study runs on, from the CLINC150 dataset.

THE DATA
--------
CLINC150 (Larson et al., EMNLP 2019, "An Evaluation Dataset for Intent
Classification and Out-of-Scope Prediction"). 150 in-scope intents grouped
into 10 domains, plus a separately collected set of OUT-OF-SCOPE queries --
real requests that the assistant was never built to handle.

    22,500 in-scope queries (150 intents x 150) · 1,200 out-of-scope queries

WHY THIS DATASET AND NOT A BIGGER ONE
-------------------------------------
Almost every public intent dataset contains only traffic the system was
designed for. That is the single most misleading property a dataset can have
if the question you are asking is "how much of this queue can we automate",
because it silently assumes the hardest input never arrives.

CLINC150 is the rare dataset built specifically to break that assumption: the
authors crowdsourced a held-out set of 1,000 test queries that belong to none
of the 150 supported intents, precisely to measure what a classifier does when
it meets something outside its world. That out-of-scope set is the reason this
analysis can produce a deployable number instead of a demo number.

The queries are short, single-intent, English, crowdsourced -- closer to chat
and in-app assistant traffic than to long email tickets. The threshold
economics generalise; the absolute accuracy on a given client's queue does not,
and nothing here claims it does.

PROVENANCE
----------
Both files are pulled from the authors' own repository at a pinned commit and
checked against recorded SHA-256 digests. If either digest fails the run stops
rather than quietly analysing something else.

Usage:  python analysis/prepare_data.py
Writes: data/contacts.csv, data/provenance.json
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

import pandas as pd

# Pinned to a commit, not to master: master can move, and a moved dataset would
# silently change every number quoted downstream.
COMMIT = "828f8093932c8fe6ca7936c3d2e52903b1c523de"
BASE = f"https://raw.githubusercontent.com/clinc/oos-eval/{COMMIT}/data"

SOURCES = {
    "data_full.json": "36923c3705a59e08fe9c3883d8bc2dd966ef93e22cb78ac41171782a698d56e0",
    "domains.json": "b947b579d3b8e74b06f93b01083d8efaff2888b43a3e362533bd88a6e1211b3a",
}

DATA = Path("data")
RAW = DATA / "raw"

# CLINC ships six splits. The names encode two independent things -- which
# split, and whether the query is in scope -- so they get unpacked into two
# columns rather than left as one opaque label.
SPLITS = {
    "train": ("train", True),
    "val": ("val", True),
    "test": ("test", True),
    "oos_train": ("train", False),
    "oos_val": ("val", False),
    "oos_test": ("test", False),
}


def fetch(name: str) -> bytes:
    """Download once, cache on disk, and verify the digest every single run."""
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / name

    if not path.exists():
        print(f"  downloading {name} ...")
        with urllib.request.urlopen(f"{BASE}/{name}", timeout=120) as r:
            path.write_bytes(r.read())

    blob = path.read_bytes()
    digest = hashlib.sha256(blob).hexdigest()
    if digest != SOURCES[name]:
        raise SystemExit(
            f"{name}: SHA-256 mismatch.\n"
            f"  expected {SOURCES[name]}\n"
            f"  got      {digest}\n"
            "The upstream file changed. Stopping rather than analysing "
            "something other than the dataset this study documents."
        )
    print(f"  {name}: sha256 ok ({len(blob):,} bytes)")
    return blob


def main() -> None:
    print("Fetching CLINC150 ...")
    full = json.loads(fetch("data_full.json"))
    domains = json.loads(fetch("domains.json"))

    # domains.json maps domain -> [intent, ...]; invert it to label each query.
    intent_domain = {i: d for d, intents in domains.items() for i in intents}
    if len(intent_domain) != 150:
        raise SystemExit(f"expected 150 mapped intents, got {len(intent_domain)}")

    rows = []
    for key, (split, in_scope) in SPLITS.items():
        for text, intent in full[key]:
            rows.append(
                {
                    "text": text,
                    "intent": intent,
                    # Out-of-scope queries genuinely have no domain -- they are
                    # not "a domain we do badly at", they are traffic the system
                    # has no concept for. Naming that explicitly keeps the
                    # per-domain results from quietly absorbing them later.
                    "domain": intent_domain[intent] if in_scope else "out_of_scope",
                    "split": split,
                    "in_scope": in_scope,
                }
            )

    contacts = pd.DataFrame(rows)

    unmapped = set(contacts.loc[contacts.in_scope, "intent"]) - set(intent_domain)
    if unmapped:
        raise SystemExit(f"intents with no domain: {sorted(unmapped)}")

    DATA.mkdir(exist_ok=True)
    contacts.to_csv(DATA / "contacts.csv", index=False)

    provenance = {
        "source": "CLINC150 (Larson et al., EMNLP 2019)",
        "repository": "https://github.com/clinc/oos-eval",
        "commit": COMMIT,
        "sha256": SOURCES,
        "rows": int(len(contacts)),
        "in_scope_rows": int(contacts.in_scope.sum()),
        "out_of_scope_rows": int((~contacts.in_scope).sum()),
        "intents": int(contacts.loc[contacts.in_scope, "intent"].nunique()),
        "domains": sorted(domains),
        "split_counts": {
            f"{split}_{'in_scope' if scope else 'out_of_scope'}": int(n)
            for (split, scope), n in contacts.groupby(["split", "in_scope"]).size().items()
        },
    }
    (DATA / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")

    print(
        f"\ndata/contacts.csv: {len(contacts):,} queries · "
        f"{provenance['in_scope_rows']:,} in scope across "
        f"{provenance['intents']} intents / {len(domains)} domains · "
        f"{provenance['out_of_scope_rows']:,} out of scope"
    )


if __name__ == "__main__":
    main()
