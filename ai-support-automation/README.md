# The 92% that wasn't — AI support automation, costed properly

**[Case study →](docs/CASE-STUDY.md)** · **[Recommendation memo →](docs/RECOMMENDATION.md)** · **[Walkthrough →](docs/WALKTHROUGH.md)**

An AI transformation assessment on the CLINC150 benchmark — 23,700 real customer requests, 150 supported intents, and 1,200 requests the system was never built to handle.

**The question:** a vendor demos a support assistant at 92.4% accuracy. What share of a live queue can actually be handled with no human, and what is that worth?

**The answer, in short:** 72.6% of contacts, worth $359,891 per 100,000. But the finding that changes where the money goes is this — **the abstention rule is worth 4× a flawless model.** Adding "if the model isn't confident, hand off" is worth $211,418. Making the classifier perfect, an unreachable ideal, would be worth $49,636. On this workload the model was never the binding constraint.

## Findings

| | |
|---|---|
| In-scope accuracy — the demo number | **92.4%** |
| The same model on a queue containing unknown requests | **75.6%** |
| Contacts handled with no human, at the recommended threshold | **72.6%** |
| Value of the abstention rule alone | **+$211,418** |
| Value of a *flawless* classifier | **+$49,636** |
| Business case overstates the physical ceiling by | **23%** |
| Full automation turns value-destroying at | **$18.08** per bad answer |

Three results drive the recommendation:

**The business case is unreachable in principle.** Its $588k assumes every contact is automatable. Requests outside the supported set have to reach a human at any model quality, so the physical ceiling is $478,909 — 23% lower, before a line of code is written.

**The dial beats the model.** Same classifier, same traffic: automate everything and the program is worth $148,473; abstain below 0.53 confidence and it is worth $359,891. Full automation is not a disaster — it is positive, which is why it survives review meetings — but it captures only 41% of what is available.

**Sequence by error rate, not coverage.** I expected coverage to vary across workflow domains and drive the rollout order. It doesn't: 12 points of spread, every domain above 80%. Error rate varies **14×** at the same threshold (0.5% in travel, 6.9% in home automation), which is a different and better sequencing variable.

## The data

[CLINC150](https://github.com/clinc/oos-eval) (Larson et al., EMNLP 2019). 150 in-scope intents across 10 domains, plus a separately crowdsourced set of **out-of-scope** queries — real requests belonging to none of the supported intents.

It was chosen for that second set. Almost every public intent dataset contains only traffic the system was designed for, which silently assumes the hardest input never arrives — the single most misleading property a dataset can have when the question is "how much of this queue can we automate." CLINC150 was built specifically to break that assumption, and it is the reason this analysis produces a deployable number instead of a demo number.

The queries are short, single-intent, crowdsourced English — closer to chat and in-app assistant traffic than to long email tickets. The threshold economics generalise; the absolute accuracy on a given client's queue does not, and nothing here claims it does.

### Provenance and verification

Nothing is hand-entered. Every number quoted in the case study, the memo and the walkthrough is read from `outputs/metrics.json`, produced by `run_analysis.py`.

| Check | Result |
|---|---|
| Upstream pinned to commit | `828f8093932c8fe6ca7936c3d2e52903b1c523de` |
| `data_full.json` SHA-256 | `36923c3705a59e08fe9c3883d8bc2dd966ef93e22c…` verified every run |
| Queries / intents / domains | 23,700 / 150 / 10 — matches the published dataset |
| Rebuild from scratch | `data/` and `outputs/` deleted and regenerated: `metrics.json` and every SVG byte-identical |

The data is pinned to a commit rather than to `master`, because a moved dataset would silently change every number downstream. If either digest fails, the run stops rather than quietly analysing something else.

## Running it

```bash
pip install -r analysis/requirements.txt
python analysis/prepare_data.py    # fetches CLINC150, verifies SHA-256 -> data/contacts.csv
python analysis/run_analysis.py    # -> outputs/metrics.json, outputs/figures/*.svg
```

Roughly two minutes end to end. Deterministic — same inputs, same numbers, byte-identical figures.

The pipeline pins BLAS to a single thread. Multi-threaded matrix products sum in whatever order the threads finish, and floating-point addition is not associative, so the same fit can land a few ulps apart on machines with different core counts. That is invisible in the headline numbers — I checked, they are unchanged — but it breaks the byte-identical property, and a reproducibility claim a reader cannot check with `diff` is not worth making. One thread costs about a minute and buys that back.

## Layout

```
analysis/prepare_data.py   fetch + verify CLINC150, build the contact log
analysis/run_analysis.py   router -> threshold sweep -> economics -> sensitivity -> figures
data/contacts.csv          23,700 queries, labelled in-scope / out-of-scope
outputs/metrics.json       every number the write-ups quote
outputs/threshold_curve.csv  the full coverage/precision/value sweep
outputs/figures/           SVG charts, embedded in the case study
docs/CASE-STUDY.md         the analysis and the argument
docs/RECOMMENDATION.md     executive memo: stage gates, risk register, what would change it
docs/WALKTHROUGH.md        presentation order, and the hard questions with answers
```

## Method notes

- **Out-of-scope examples are withheld from training,** deliberately. That is the real deployment condition: you cannot label the requests nobody has thought of yet. Training on them would measure a system that cannot exist.
- **The threshold is selected on validation and reported on test.** Selecting it on the reported data would inflate everything downstream. It moves 0.025 between the two — worth $1,636 on $360k — which is the evidence that it is stable rather than tuned.
- **Logistic regression over a fine-tuned transformer,** deliberately. The whole analysis turns on the *confidence score*, so a model whose probabilities are meaningful and inspectable matters more than one that scores a point higher. The obvious objection is answered quantitatively rather than waved at: a *perfect* in-scope classifier is measured, and it is worth a fifth of the routing rule. Any real model lands below that ceiling, so the ranking holds by construction.
- **Cost inputs are judgments, not computations.** No transcript log knows what a support contact costs. They are declared at the top of the script and swept, so a reader can disagree with the input rather than with the arithmetic.
- **The out-of-scope mix rate is an explicit parameter,** not whatever ratio the test files happen to contain. In-scope and out-of-scope results are combined by a stated weight, so the traffic assumption stays visible and sweepable.
- **The perfect-model and perfect-routing scenarios are idealisations** — they remove errors while holding the confidence distribution fixed, which is not how a real model improves. They are used only as upper bounds, which is all they can support.
- **The per-domain cut is in-scope only.** Out-of-scope contacts belong to no domain, so charging them to one would invent a finding. Unknown traffic is a system-level cost and is reported as one.

## What this does not show

A public benchmark is not client data. This models single-turn routing, assumes every wrong answer costs the same, and cannot see intent drift, multi-intent contacts, or adversarial users. The stage gates in the memo exist to test the benchmark-transfer assumption before any customer is exposed to it.
