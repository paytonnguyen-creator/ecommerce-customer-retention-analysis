# Walking through this project

The argument in the order I'd present it, and the questions I'd expect back.

---

## The 60-second version

> CDNOW was an online music retailer. I looked at their real transaction log —
> 23,570 customers, all acquired in one quarter, followed for 18 months.
>
> 62% never came back. So the obvious move is to build a model that predicts
> who will, and spend the retention budget on them. I built it, and it doesn't
> work — 0.576 AUC against a 0.375 base rate. A single first transaction just
> doesn't carry much signal about a person.
>
> But the timing data does. When customers come back, the median gap is 57
> days, and about 60% of second purchases land inside 90 days. So the window is
> short and known even though the *people* aren't identifiable.
>
> That flips the recommendation. Don't build the targeting model — build a
> timed treatment and give it to everyone. I sized it at roughly $40k of
> incremental repeat revenue on a deliberately conservative assumption, and
> wrote it up as a PRD with a kill threshold.

The point to land: **the negative result is the finding.** A weak model didn't
end the analysis, it changed the recommendation.

---

## The 5-minute version — four beats

**1. Frame the decision, not the topic.**
"Improve retention" isn't answerable. The real question was: does the next unit
of effort go into a model that predicts who returns, or a treatment applied to
everyone? Those are different budgets and different owners. Naming the decision
first is what makes the analysis capable of being wrong.

**2. Sort findings into observable vs. actionable.**
Lifetime spend predicts retention beautifully and is completely useless — you
can't *assign* someone a high lifetime spend. Every result got sorted before it
was allowed near a recommendation.

**3. The load-bearing finding is a negative one.**
0.576 AUC. Weak prediction is normally a disappointing result. Here it's the
input to the decision: you can't target, so don't build targeting.

**4. Kill your best-looking lever.**
"More titles in the first order" was a 15pp gap across 11,920 customers — the
biggest number in the analysis. Basket value and title count correlate 0.75,
and once value is controlled the title coefficient collapses from +0.22 to
+0.04. People come back because they *spent* more, not because they bought more
things. Acting on the raw gap pushes merchandising toward cheap add-ons —
moving the metric without moving the business.

---

## Numbers worth knowing cold

| | |
|---|---|
| Customers / orders | 23,570 / 67,591 |
| Never repeat within 180 days | 62.5% |
| Median days to second purchase | 57 |
| Second purchases inside 90 days | ~60% |
| Revenue from top 20% of customers | 67.8% |
| Hold-out AUC / base rate | 0.576 / 0.375 |
| Title count: alone → controlled | +0.22 → +0.04 |
| Correlation, basket value vs. title count | 0.75 |
| Recommended lever | ~$39.7k, Low effort |

---

## Questions I'd expect, and the honest answers

**"Your model is barely better than a coin. Isn't that a failed project?"**
It would be if prediction were the goal. The goal was a decision, and a weak
model answers it — it rules out the targeting build. I'd rather report a real
0.576 than tune until something looks impressive.

**"Why logistic regression and not gradient boosting?"**
Because the deliverable is an argument someone non-technical has to be able to
check. Coefficients are legible; feature importances aren't. I traded a little
accuracy for auditability. Given the ceiling was 0.576, a fancier model would
have bought very little anyway.

**"How do you know the title-count effect is confounded rather than real?"**
I don't know it, I tested it. The two variables correlate 0.75, and the
coefficient collapses 82% under control. That's consistent with confounding and
inconsistent with an independent effect. Settling it properly needs an
experiment, which is why the PRD proposes a holdout rather than asserting a
causal claim.

**"Where did the $39.7k come from?"**
Population × assumed lift × value per repeater. The lift is **3pp and it's
assumed, not measured** — it's the weakest number in the project and I've
flagged it as such everywhere. It's the thing the holdout exists to prove or
kill. I picked a deliberately modest figure rather than one that made the slide
look better.

**"This data is from 1997. So what?"**
The structural patterns — heavy one-and-done, concentrated revenue, a short
second-purchase window — still hold in subscription and e-commerce businesses.
The 1997 channel tactics don't transfer, so I don't propose any. I picked this
dataset for its cohort design: everyone acquired in one quarter and observed
15+ months, so the repeat window is fully observed for every customer and the
usual censoring judgment call disappears.

**"What would you do differently?"**
Model time-to-second-purchase directly with survival analysis. A binary
"returned in 180 days" throws away the timing information that turned out to be
the most useful thing in the dataset. I reached for logistic regression first
and should have reached for a hazard model.

**"What's the weakest part?"**
The 3pp assumption, and the fact that the dataset has no channel, category or
discount fields. Those three would have let me test whether discount-led
acquisition explains the low-value, low-retention segment, which is the
hypothesis I most wanted to check and couldn't.

---

## What not to claim

- Don't say the model "works." It doesn't, and that's the point.
- Don't present $39.7k as a forecast. It's a sizing on a stated assumption.
- Don't call anything here causal. It's observational; the PRD proposes the
  experiment that would make a causal claim available.
