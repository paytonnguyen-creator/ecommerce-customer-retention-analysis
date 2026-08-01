# Walkthrough

The argument in the order I would present it, and the questions that come after.

---

## The 60-second version

> A vendor demos a support AI at 92% accuracy and builds a business case on automating the queue. I rebuilt that analysis on a benchmark that includes something most datasets leave out — 1,200 real customer requests the system was never designed to handle.
>
> Two things fell out. First, the business case was unreachable in principle: requests outside the supported set have to reach a human, so the physical ceiling is 23% below the number in the deck, before anyone writes code.
>
> Second, and this is the part I'd lead with — the highest-value change wasn't the model. Adding one rule, "if the model isn't confident, hand off immediately," was worth $211k per 100,000 contacts. Making the classifier *flawless* — not better, perfect — would be worth $50k. The routing decision beat the impossible model upgrade by four times.
>
> So the recommendation was to spend the first dollar on the handoff design and on measuring how much unknown traffic the queue actually carries, and not on model quality.

---

## The five slides

**1. The demo number and the queue number.** 92.4% in-scope accuracy. Blend in unknown traffic at the rate the dataset's authors designed for and it's 75.6%. Nothing about the model changed. *Point: benchmarks measure the world the system was built for; queues don't.*

**2. Accuracy is the wrong unit.** A declined contact costs one human touch. A confidently wrong one costs the touch, the rework, and the customer. Accuracy scores these the same; a P&L doesn't. *Point: this is an exposure decision, not a scoring decision.*

**3. The dial.** Sweep the confidence threshold, price each point. Automate everything: $148k. Abstain below 0.53: $360k. *Point: same model, same traffic, 2.4× the value.*

**4. The leverage ranking.** Routing rule +$211k. Flawless classifier +$50k. Perfect unknown-request detection +$25k. *Point: rank interventions before buying any of them.*

**5. What I'd do Monday.** Sample 500 contacts to measure the real out-of-scope rate. Shadow-mode before exposure. Per-domain thresholds — error rates vary 14× across domains at one threshold. Instrument the silent failure. *Point: the gates have numbers and defined failure actions.*

---

## Hard questions

**"Your classifier is TF-IDF and logistic regression. A frontier LLM would crush it — doesn't that invalidate the whole thing?"**

It would beat it on accuracy, and it wouldn't change the recommendation. I measured the ceiling: a *perfect* in-scope classifier — zero errors, which no model achieves — adds $49,636. The routing rule adds $211,418. Any real LLM lands somewhere below the perfect ceiling, so the ranking is safe by construction. That's why I framed it as an upper bound instead of arguing about model choice.

There's a second reason for the linear model that matters more than it sounds: this analysis turns entirely on the *confidence score*, so I wanted a model whose probabilities mean something and are inspectable, not one point of accuracy with opaque scores.

**"Where did $6.00 and $12.00 come from?"**

They're judgments, not measurements — no transcript log knows what a contact costs. That's exactly why they're declared as inputs at the top of the script and swept rather than buried. The interesting output isn't the base case, it's the break-even: **full automation turns value-destroying at $18.08 per bad answer**. That single number reframes the conversation, because a client can usually tell you whether a wrong answer costs them more or less than $18 even when they can't give you a point estimate.

And the thresholded policy stays positive across every value I tested, which is the actual argument for it — not that it earns more at the base case, but that it keeps earning when the base case is wrong.

**"18.2% out-of-scope seems high. Isn't that doing all the work?"**

It's the blend CLINC's authors built into their own test split, not a number I picked to make a point. And it's the first thing I'd tell a client to measure rather than argue about, because value falls almost linearly in it — $467k at 0%, $231k at 40%. Sampling a few hundred contacts settles it in a day. That's why "measure it" is recommendation two and not a footnote.

**"You picked the threshold that maximises your own metric. Isn't that circular?"**

The threshold is selected on the validation split and reported on test. If I'd picked it on test, every number downstream would be inflated. The test-optimal threshold would have been 0.500 versus the 0.525 I selected — a $1,636 difference on $360k. That gap is small on purpose: it's the evidence the choice is stable rather than tuned.

**"Your whole policy is a confidence threshold. Is that score even calibrated?"**

Not as a probability, no — and I checked rather than assuming. On supported traffic the router is under-confident in every bin: when it claims 15% it's right 54% of the time. That's the safe direction to be wrong in, and it's why a 0.53 threshold delivers 95.1% actual accuracy. The score works as a *ranking* — AUROC 0.95 for separating supported from unsupported traffic — which is all the policy needs.

The more interesting bit is what it does to monitoring. Expected calibration error is 0.098 on supported traffic and *improves* to 0.050 on the live queue, because out-of-scope contacts are always wrong and pile into the low-confidence bins, cancelling the under-confidence. So the calibration metric gets better as the queue gets worse. If a client monitors pooled calibration as a health signal, rising unknown traffic reads as an improvement. I'd track the signed gap separately for supported and unsupported traffic, never pooled.

**"Isn't 'automate everything is bad' obvious?"**

The direction is. The magnitude isn't, and the magnitude is the decision. Full automation is still *positive* here — $148k. It's not a disaster, which is precisely why it survives review meetings. The finding is that it captures only 41% of what's available, and that the fix is a routing rule rather than a model. Nobody argues against confidence thresholds in the abstract; plenty of programs ship without one because deflection rate is the metric on the dashboard.

**"What did you get wrong?"**

Two things, and I left both in the repo history. I predicted the confidence distributions would overlap badly and that unknown-request detection would be the binding constraint. It wasn't — AUROC 0.95, better than I expected, and a perfect classifier turned out to be worth twice what perfect detection was worth. I had written a chart title asserting the opposite before I computed it.

I also assumed coverage would vary a lot by domain and drive the rollout sequence. It doesn't — 12 points of spread, all above 80%. The real spread was in *error rate*, 14× across domains, which is a better sequencing variable and a different recommendation than the one I started to write.

**"What would make you walk this back?"**

Shadow-mode accuracy more than 5pp below benchmark — benchmark transfer is the biggest untested assumption here. Or no abstention path in the product, which deletes the entire $211k advantage and reverts the decision to the much weaker full-automation case.

---

## What I'd want to do next

- **Multi-turn.** This models single-turn routing. Real assistants escalate mid-conversation, and the cost of a bad handoff three turns in is not the cost of a bad handoff at turn one.
- **Non-uniform error cost.** I assume every wrong answer costs the same. A wrong billing answer and a wrong store-hours answer obviously don't, and modelling that properly would probably push the per-domain thresholds further apart than I already recommend.
- **Drift over time.** Supported intents decay as products change. The static snapshot here can't see that, and it's the failure mode most likely to erode the value after year one.
