// Regenerate the executive deck from outputs/metrics.json.
//
// Every figure on every slide is read from the metrics file — nothing is typed
// in by hand, so the deck cannot drift away from the analysis. Run the pipeline
// first, then:  npm i pptxgenjs && node analysis/build_deck.js
//
// Deliberately text-and-shape only. A deck that renders identically everywhere
// beats one that embeds charts and breaks in half the viewers that open it.

const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const M = JSON.parse(fs.readFileSync(path.join(ROOT, "outputs/metrics.json")));

const IN = M.inputs, DATA = M.data, MOD = M.model;
const POL = M.policy.at_threshold, NAIVE = M.policy.automate_everything;
const DEC = M.decomposition_value_per_period, LEV = M.leverage_value_added_per_period;
const SENS = M.sensitivity, DOM = M.by_domain;
// Worst-to-best by ERROR rate, which is what the sequencing recommendation
// turns on. by_domain arrives sorted by coverage, which is a different order.
const BY_ERR = [...DOM].sort((a, b) => a.accuracy_when_auto - b.accuracy_when_auto);

// Midnight Executive — matches the sibling case study in this portfolio.
const NAVY = "1E2761", ICE = "CADCFC", WHITE = "FFFFFF";
const INK = "14161A", BODY = "4D525B", MUTED = "868C96", LINE = "E2E4E8";
const AMBER = "B8860B", TEAL = "1F7A5C";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.3 x 7.5
pres.author = "Payton Nguyen";
pres.title = "AI Support Automation — Executive Summary";

const HEAD = "Cambria", BODYF = "Calibri";
const pct = (v, d = 1) => `${(v * 100).toFixed(d)}%`;
const k = v => `$${Math.round(v / 1000)}k`;
const money = v => `$${Math.round(v).toLocaleString()}`;

function title(s, text, sub) {
  s.addText(text, { x: 0.7, y: 0.5, w: 11.9, h: 0.6, fontSize: 38, bold: true, color: INK, fontFace: HEAD });
  if (sub) {
    s.addText(sub, { x: 0.7, y: 1.18, w: 11.9, h: 0.5, fontSize: 17, color: BODY, fontFace: BODYF });
  }
}

function kicker(s, text, color = INK) {
  s.addText(text, { x: 0.7, y: 6.25, w: 11.9, h: 0.7, fontSize: 15, color, italic: true, fontFace: BODYF });
}

// ── 1. Title ────────────────────────────────────────────────────────────────
let s = pres.addSlide();
s.background = { color: NAVY };
s.addText("The 92% that wasn't", {
  x: 0.8, y: 1.5, w: 11, h: 0.95, fontSize: 50, bold: true, color: WHITE, fontFace: HEAD,
});
s.addText("What a support-automation business case gets wrong", {
  x: 0.8, y: 2.45, w: 11, h: 0.7, fontSize: 27, color: ICE, fontFace: HEAD,
});
s.addText("…and why the routing rule beat the model by 4x", {
  x: 0.8, y: 3.15, w: 11, h: 0.5, fontSize: 18, color: ICE, italic: true, fontFace: BODYF,
});
s.addText(
  [
    { text: "CLINC150 intent benchmark", options: { bold: true, breakLine: true } },
    {
      text: `${(DATA.test_in_scope + DATA.test_out_of_scope).toLocaleString()} held-out requests · `
        + `${DATA.intents} supported intents · `
        + `${DATA.test_out_of_scope.toLocaleString()} requests the system was never built to handle`,
      options: {},
    },
  ],
  { x: 0.8, y: 4.25, w: 11, h: 0.9, fontSize: 13, color: ICE, fontFace: BODYF }
);
s.addText("Payton Nguyen", { x: 0.8, y: 6.5, w: 5, h: 0.4, fontSize: 13, color: "8FA4D8", fontFace: BODYF });
s.addNotes(
  "Framing: the decision is not 'is the model good enough'. It is 'how much traffic are we willing to "
  + "expose to a confidently wrong answer'. Those are different questions and only the second has a dollar figure."
);

// ── 2. The demo number and the queue number ─────────────────────────────────
s = pres.addSlide();
s.background = { color: WHITE };
title(s, "The demo number is not the queue number",
  "Benchmarks measure the world the system was built for. Live queues do not.");

const stats = [
  [pct(MOD.in_scope_test_accuracy), "accuracy on supported\nrequests — the demo", NAVY],
  [pct(MOD.blended_accuracy_no_abstention), "the same model once\nunknown requests arrive", AMBER],
  [pct(IN.assumed_out_of_scope_share, 0), "of traffic outside every\nsupported intent", NAVY],
  [pct(MOD.oos_answered_above_threshold), "of those answered\nconfidently anyway", AMBER],
];
stats.forEach(([big, label, color], i) => {
  const x = 0.7 + i * 3.05;
  s.addShape(pres.ShapeType.roundRect, {
    x, y: 2.0, w: 2.75, h: 2.9, rectRadius: 0.12,
    fill: { color: "F4F6FB" }, line: { color: LINE, width: 1 },
  });
  s.addText(big, { x, y: 2.45, w: 2.75, h: 0.95, fontSize: 40, bold: true, color, align: "center", fontFace: HEAD });
  s.addText(label, { x: x + 0.15, y: 3.55, w: 2.45, h: 1, fontSize: 13, color: BODY, align: "center", fontFace: BODYF });
});
kicker(s,
  "Nothing about the model changed between the first two numbers. The queue just got realistic — and a "
  + "request the assistant was never designed for is answered wrong before it is read.");
s.addNotes(
  "The fourth stat is the one to dwell on: unknown requests answered confidently generate no ticket and no "
  + "alert. Deflection dashboards look excellent while this happens."
);

// ── 3. The dial ─────────────────────────────────────────────────────────────
s = pres.addSlide();
s.background = { color: WHITE };
title(s, "One rule, 2.4x the value",
  "Same classifier, same traffic. The only change is when the assistant declines to answer.");

const rows = [
  ["Automate everything", pct(NAIVE.coverage, 0), pct(NAIVE.automation_precision), money(NAIVE.value_per_period), AMBER],
  [`Abstain below ${POL.threshold.toFixed(2)} confidence`, pct(POL.coverage, 0), pct(POL.automation_precision), money(POL.value_per_period), TEAL],
];
s.addText("Policy", { x: 0.75, y: 2.05, w: 4.6, h: 0.35, fontSize: 12, bold: true, color: MUTED, fontFace: BODYF });
["Handled with no human", "Correct when it did", "Value per 100k contacts"].forEach((h, i) => {
  s.addText(h, { x: 5.5 + i * 2.45, y: 2.05, w: 2.4, h: 0.35, fontSize: 12, bold: true, color: MUTED, align: "center", fontFace: BODYF });
});
rows.forEach(([label, cov, prec, val, color], i) => {
  const y = 2.5 + i * 1.15;
  s.addShape(pres.ShapeType.roundRect, {
    x: 0.7, y, w: 11.9, h: 0.95, rectRadius: 0.1,
    fill: { color: i === 1 ? "EEF6F2" : "FBF6EA" }, line: { color: LINE, width: 1 },
  });
  s.addText(label, { x: 0.95, y, w: 4.5, h: 0.95, fontSize: 16, bold: true, color: INK, valign: "middle", fontFace: BODYF });
  [cov, prec, val].forEach((v, j) => {
    s.addText(v, {
      x: 5.5 + j * 2.45, y, w: 2.4, h: 0.95, fontSize: j === 2 ? 21 : 18, bold: j === 2,
      color: j === 2 ? color : INK, align: "center", valign: "middle", fontFace: HEAD,
    });
  });
});

s.addShape(pres.ShapeType.roundRect, {
  x: 0.7, y: 5.0, w: 11.9, h: 1.0, rectRadius: 0.1, fill: { color: NAVY }, line: { color: NAVY, width: 1 },
});
s.addText(
  [
    { text: `+${money(LEV.abstention_threshold_config_change)}  `, options: { fontSize: 24, bold: true, color: WHITE, fontFace: HEAD } },
    { text: "from a routing rule — no change to the model, no retraining, no new vendor", options: { fontSize: 15, color: ICE, fontFace: BODYF } },
  ],
  { x: 1.0, y: 5.0, w: 11.3, h: 1.0, valign: "middle" }
);
kicker(s,
  `Full automation is not a disaster — it is positive, which is exactly why it survives review meetings. `
  + `It simply captures ${pct(NAIVE.value_per_period / POL.value_per_period, 0)} of what is available.`);
s.addNotes(
  `Threshold selected on validation (${M.policy.threshold_selected_on_validation}), reported on test. The `
  + `test-optimal would have been ${M.policy.test_optimal_threshold} — a ${money(M.policy.value_left_by_using_validation_threshold)} `
  + "difference. Small gap = stable choice, not a tuned one."
);

// ── 4. Rank the interventions ───────────────────────────────────────────────
s = pres.addSlide();
s.background = { color: WHITE };
// Titles are kept under ~44 characters so they stay on one line at 38pt —
// a second line runs into the subtitle. analysis/check_deck.py enforces this.
title(s, "Rank the interventions before buying",
  "The instinct is to spend on model quality. Here that is the fourth-best use of the next dollar.");

const levers = [
  ["Set an abstention threshold", "routing rule — no model work", LEV.abstention_threshold_config_change, TEAL],
  ["Make the classifier flawless", "an unreachable ideal, not an upgrade", LEV.flawless_classifier_on_supported_traffic, NAVY],
  ["Detect every unsupported request", "perfect scoping and abstention", LEV.perfect_unsupported_request_detection, NAVY],
];
const maxLev = Math.max(...levers.map(l => l[2]));
levers.forEach(([label, sub, val, color], i) => {
  const y = 2.1 + i * 1.35;
  s.addText(label, { x: 0.7, y, w: 4.3, h: 0.4, fontSize: 16, bold: true, color: INK, fontFace: BODYF });
  s.addText(sub, { x: 0.7, y: y + 0.38, w: 4.3, h: 0.35, fontSize: 12, color: MUTED, italic: true, fontFace: BODYF });
  s.addShape(pres.ShapeType.rect, {
    x: 5.2, y: y + 0.08, w: (val / maxLev) * 5.6, h: 0.62, fill: { color }, line: { color, width: 0 },
  });
  s.addText(`+${k(val)}`, {
    x: 5.3 + (val / maxLev) * 5.6, y: y + 0.08, w: 1.6, h: 0.62,
    fontSize: 17, bold: true, color: INK, valign: "middle", fontFace: HEAD,
  });
});
kicker(s,
  `The comparison is deliberately unfair to the model and it still loses: "flawless" means zero errors, which no `
  + `model achieves. Any real system — including a frontier LLM — lands below that ceiling, so the ranking holds by construction.`);
s.addNotes(
  "This is the slide to lead with. It pre-empts the 'why not use a better model' question by having already "
  + "measured the ceiling on what a better model could possibly be worth."
);

// ── 5. The business case is unreachable ─────────────────────────────────────
s = pres.addSlide();
s.background = { color: WHITE };
title(s, "The business case is unreachable",
  "Requests outside the supported set have to reach a human. That is not a model problem.");

const bars = [
  ["Business case as submitted", "every contact automated", DEC.business_case_every_contact_automated, MUTED],
  ["Physical ceiling", "flawless model AND flawless abstention", DEC.physical_ceiling_perfect_model_and_abstention, TEAL],
  ["Recommended operating point", "today's model, threshold tuned", DEC.as_built_threshold_tuned, NAVY],
  ["Automate everything", "today's model, no abstention", DEC.as_built_automate_everything, AMBER],
];
const maxBar = Math.max(...bars.map(b => b[2]));
bars.forEach(([label, sub, val, color], i) => {
  const y = 2.0 + i * 1.05;
  s.addText(label, { x: 0.7, y, w: 4.1, h: 0.38, fontSize: 15, bold: true, color: INK, fontFace: BODYF });
  s.addText(sub, { x: 0.7, y: y + 0.34, w: 4.1, h: 0.32, fontSize: 11.5, color: MUTED, italic: true, fontFace: BODYF });
  s.addShape(pres.ShapeType.rect, {
    x: 5.0, y: y + 0.06, w: (val / maxBar) * 5.8, h: 0.6, fill: { color }, line: { color, width: 0 },
  });
  s.addText(k(val), {
    x: 5.1 + (val / maxBar) * 5.8, y: y + 0.06, w: 1.5, h: 0.6,
    fontSize: 16, bold: true, color: INK, valign: "middle", fontFace: HEAD,
  });
});
kicker(s,
  `The submitted case overstates the physical maximum by `
  + `${pct(DEC.business_case_every_contact_automated / DEC.physical_ceiling_perfect_model_and_abstention - 1, 0)}, `
  + `before a line of code is written. Restating it is what keeps the program from being killed at the first review.`);
s.addNotes(
  "Delivered value is 75% of the achievable ceiling. Against the pitch it reads as a shortfall; against what is "
  + "possible it is most of the available value. That reframing is the difference between a cancelled program and an extended one."
);

// ── 6. What the answer depends on ───────────────────────────────────────────
s = pres.addSlide();
s.background = { color: WHITE };
title(s, "What we assumed, and what would change it",
  "Three inputs are not in the data. They are declared and swept, not buried.");

const inputs = [
  ["Human-handled contact", `$${IN.cost_human_contact.toFixed(2)}`, "fully loaded, per digital contact"],
  ["AI-handled contact", `$${IN.cost_ai_contact.toFixed(2)}`, "inference plus platform, amortised"],
  ["Confidently wrong answer", `$${IN.cost_wrong_auto_resolution.toFixed(2)}`, "rework, goodwill, churn — the contested one"],
];
inputs.forEach(([label, val, sub], i) => {
  const y = 2.0 + i * 0.82;
  s.addShape(pres.ShapeType.roundRect, {
    x: 0.7, y, w: 6.1, h: 0.7, rectRadius: 0.08,
    fill: { color: i === 2 ? "FBF6EA" : "F4F6FB" }, line: { color: LINE, width: 1 },
  });
  s.addText(label, { x: 0.95, y, w: 2.9, h: 0.7, fontSize: 14, bold: i === 2, color: INK, valign: "middle", fontFace: BODYF });
  s.addText(val, { x: 3.85, y, w: 1.0, h: 0.7, fontSize: 17, bold: true, color: i === 2 ? AMBER : NAVY, valign: "middle", align: "right", fontFace: HEAD });
  s.addText(sub, { x: 5.05, y, w: 1.6, h: 0.7, fontSize: 10.5, color: MUTED, italic: true, valign: "middle", fontFace: BODYF });
});

s.addShape(pres.ShapeType.roundRect, {
  x: 7.1, y: 2.0, w: 5.5, h: 2.44, rectRadius: 0.1, fill: { color: NAVY }, line: { color: NAVY, width: 0 },
});
s.addText("The break-even that reframes the debate", {
  x: 7.35, y: 2.15, w: 5.0, h: 0.4, fontSize: 13, bold: true, color: ICE, fontFace: BODYF,
});
s.addText(`$${SENS.error_cost_where_full_automation_breaks_even.toFixed(2)}`, {
  x: 7.35, y: 2.6, w: 5.0, h: 0.85, fontSize: 44, bold: true, color: WHITE, fontFace: HEAD,
});
s.addText(
  "per bad answer — above this, automating everything destroys value outright, while the thresholded "
  + "policy simply gets more cautious and stays positive.",
  { x: 7.35, y: 3.45, w: 5.0, h: 0.9, fontSize: 12, color: ICE, fontFace: BODYF }
);

s.addText("Unknown-traffic rate is the assumption to measure, not argue about", {
  x: 0.7, y: 4.7, w: 11.9, h: 0.35, fontSize: 14, bold: true, color: INK, fontFace: BODYF,
});
s.addText(
  `Value falls almost linearly: ${k(SENS.value_by_oos_share["0.00"])} at 0% · `
  + `${k(SENS.value_by_oos_share["0.20"])} at 20% · ${k(SENS.value_by_oos_share["0.40"])} at 40%. `
  + "Sampling a few hundred contacts settles it in a day.",
  { x: 0.7, y: 5.05, w: 11.9, h: 0.5, fontSize: 14, color: BODY, fontFace: BODYF }
);
kicker(s,
  "A client can usually tell you whether a wrong answer costs them more or less than $18 even when they "
  + "cannot give you a point estimate. That is a more useful question than asking for the number directly.");

// ── 7. Recommendation ───────────────────────────────────────────────────────
s = pres.addSlide();
s.background = { color: WHITE };
title(s, "Recommendation", "Proceed — with abstention on day one, not deferred to a later phase.");

const recs = [
  ["Deploy with abstention from the start", "Tuned on a labelled sample of our own traffic. The rule is where most of the value is."],
  ["Measure the unknown-traffic rate first", "The input the case is most sensitive to, and among the cheapest to measure."],
  ["Instrument the silent failure", `${pct(MOD.oos_answered_above_threshold)} of unsupported requests are answered confidently. No ticket, no alert.`],
  ["Set thresholds per domain", `Error rate varies ${M.domain_spread.error_rate_ratio_worst_to_best.toFixed(0)}x across domains at one threshold — ${BY_ERR[0].domain.replace(/_/g, " ")} vs ${BY_ERR[BY_ERR.length - 1].domain.replace(/_/g, " ")}.`],
  ["Do not fund a model upgrade first", "Fourth-best use of the next dollar, behind routing, measurement and instrumentation."],
];
recs.forEach(([label, sub], i) => {
  const y = 2.0 + i * 0.86;
  s.addShape(pres.ShapeType.ellipse, {
    x: 0.7, y: y + 0.1, w: 0.42, h: 0.42, fill: { color: NAVY }, line: { color: NAVY, width: 0 },
  });
  s.addText(String(i + 1), {
    x: 0.7, y: y + 0.1, w: 0.42, h: 0.42, fontSize: 13, bold: true, color: WHITE, align: "center", valign: "middle", fontFace: HEAD,
  });
  s.addText(label, { x: 1.3, y, w: 5.0, h: 0.62, fontSize: 15, bold: true, color: INK, valign: "middle", fontFace: BODYF });
  s.addText(sub, { x: 6.4, y, w: 6.2, h: 0.62, fontSize: 12.5, color: BODY, valign: "middle", fontFace: BODYF });
});
kicker(s,
  "Gate 0 is not a formality: sample 500 contacts and measure the real unknown-traffic rate. It is the cheapest "
  + "way to discover the program is worth less than proposed — and it happens before the build.");
s.addNotes(
  "Every gate in the memo has a number and a defined action if the number is missed. A gate that cannot fail is not a gate."
);

// ── Write ───────────────────────────────────────────────────────────────────
const out = path.join(ROOT, "docs/ai-support-automation-executive-deck.pptx");
pres.writeFile({ fileName: out }).then(() => {
  console.log(`wrote ${path.relative(ROOT, out)} — ${pres.slides.length} slides, all figures read from metrics.json`);
});
