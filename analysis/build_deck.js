const pptxgen = require("pptxgenjs");
const fs = require("fs");

const M = JSON.parse(fs.readFileSync("/home/user/ecommerce-customer-retention-analysis/outputs/metrics.json"));
const H = M.headline, MD = M.model;
const opp = Object.fromEntries(M.opportunity.map(o => [o.verdict + "|" + o.lever.slice(0, 12), o]));
const nudge = M.opportunity.find(o => o.lever.startsWith("Timed"));
const basket = M.opportunity.find(o => o.lever.startsWith("Lift"));
const titles = M.opportunity.find(o => o.lever.startsWith("Get a 2nd"));
const cohort = M.opportunity.find(o => o.lever.startsWith("Raise"));

// Midnight Executive — navy dominant, ice blue support, amber accent for the one warning.
const NAVY = "1E2761", ICE = "CADCFC", WHITE = "FFFFFF";
const INK = "14161A", BODY = "4D525B", MUTED = "868C96", LINE = "E2E4E8", AMBER = "B8860B";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";           // 13.3 x 7.5
pres.author = "Payton Nguyen";
pres.title = "CDNOW Retention — Executive Summary";

const HEAD = "Cambria", BODYF = "Calibri";
const pct = v => `${(v * 100).toFixed(1)}%`;
const k = v => `$${(v / 1000).toFixed(1)}k`;

// ── 1. Title (dark) ─────────────────────────────────────────────────────────
let s = pres.addSlide();
s.background = { color: NAVY };
s.addText("Retention", { x: 0.8, y: 1.5, w: 8, h: 0.9, fontSize: 54, bold: true, color: WHITE, fontFace: HEAD });
s.addText("Why 62% of customers never came back", {
  x: 0.8, y: 2.35, w: 9.5, h: 0.7, fontSize: 30, color: ICE, fontFace: HEAD,
});
s.addText("…and why a prediction model was the wrong fix", {
  x: 0.8, y: 3.05, w: 9.5, h: 0.5, fontSize: 18, color: ICE, italic: true, fontFace: BODYF,
});
s.addText(
  [
    { text: "CDNOW transaction log", options: { bold: true, breakLine: true } },
    { text: `${M.source.customers.toLocaleString()} customers · ${M.source.orders.toLocaleString()} orders · Q1 1997 cohort, followed to June 1998`, options: {} },
  ],
  { x: 0.8, y: 4.15, w: 9, h: 0.9, fontSize: 13, color: ICE, fontFace: BODYF }
);
s.addText("Payton Nguyen", { x: 0.8, y: 6.5, w: 5, h: 0.4, fontSize: 13, color: "8FA4D8", fontFace: BODYF });
s.addNotes("Framing: the decision was not 'how do we improve retention' but 'do we build a targeting model or a treatment for everyone'. Those are different programs with different costs.");

// ── 2. The problem, as four stats ───────────────────────────────────────────
s = pres.addSlide();
s.background = { color: WHITE };
s.addText("The problem", { x: 0.7, y: 0.55, w: 9, h: 0.6, fontSize: 40, bold: true, color: INK, fontFace: HEAD });
s.addText("Most customers buy once, and revenue leans hard on a few.", {
  x: 0.7, y: 1.25, w: 11, h: 0.45, fontSize: 17, color: BODY, fontFace: BODYF,
});

const stats = [
  [pct(H.one_and_done_share), "never place a\nsecond order"],
  [`${H.median_days_to_second.toFixed(0)} days`, "median gap to the\nsecond purchase"],
  [`${H.revenue_share_top_20pct.toFixed(0)}%`, "of revenue from the\ntop 20% of customers"],
  [`${MD.auc.toFixed(3)}`, "hold-out AUC —\nbarely above chance"],
];
stats.forEach(([big, label], i) => {
  const x = 0.7 + i * 3.05;
  s.addShape(pres.ShapeType.roundRect, {
    x, y: 2.05, w: 2.75, h: 2.9, rectRadius: 0.12,
    fill: { color: "F4F6FB" }, line: { color: LINE, width: 1 },
  });
  s.addText(big, { x, y: 2.5, w: 2.75, h: 0.95, fontSize: 40, bold: true, color: NAVY, align: "center", fontFace: HEAD });
  s.addText(label, { x: x + 0.15, y: 3.6, w: 2.45, h: 1, fontSize: 13, color: BODY, align: "center", fontFace: BODYF });
});

s.addText(
  "Read the concentration the other way round: acquisition spend is going to a majority of customers who return nothing after the first basket.",
  { x: 0.7, y: 5.45, w: 11.9, h: 0.7, fontSize: 15, color: INK, italic: true, fontFace: BODYF }
);
s.addNotes("62.5% one-and-done. The top-heavy revenue split is usually read as good news about whales; the useful reading is the inverse.");

// ── 3. What the data said — chart + the rejected lever ──────────────────────
s = pres.addSlide();
s.background = { color: WHITE };
s.addText("What the data said", { x: 0.7, y: 0.55, w: 9, h: 0.6, fontSize: 40, bold: true, color: INK, fontFace: HEAD });
s.addText("When customers return, they return fast — that is the whole opening.", {
  x: 0.7, y: 1.25, w: 11, h: 0.45, fontSize: 17, color: BODY, fontFace: BODYF,
});

const w = M.second_purchase_window.share;
const order = ["0-30", "31-60", "61-90", "91-120", "121-180", "181-270", "271-365", "365+"];
s.addChart(pres.ChartType.bar, [{
  name: "Share of repeat buyers",
  labels: order,
  values: order.map(o => w[o]),
}], {
  x: 0.7, y: 1.95, w: 7.1, h: 4.1,
  barDir: "col", chartColors: [NAVY],
  showTitle: true, title: "Days between first and second purchase (%)",
  titleFontSize: 13, titleColor: MUTED, titleFontFace: BODYF,
  showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 10,
  dataLabelColor: INK, dataLabelFormatCode: "0",
  showLegend: false, catAxisLabelColor: MUTED, valAxisLabelColor: MUTED,
  catAxisLabelFontSize: 10, valAxisLabelFontSize: 10,
  valGridLine: { color: LINE, size: 1 }, catGridLine: { style: "none" },
  valAxisMaxVal: 45,
});

s.addShape(pres.ShapeType.roundRect, {
  x: 8.15, y: 1.95, w: 4.45, h: 1.95, rectRadius: 0.12,
  fill: { color: "F4F6FB" }, line: { color: LINE, width: 1 },
});
s.addText("~60%", { x: 8.35, y: 2.15, w: 4, h: 0.7, fontSize: 34, bold: true, color: NAVY, fontFace: HEAD });
s.addText("of second purchases land inside 90 days. The window to act in is short and known.", {
  x: 8.35, y: 2.85, w: 4.05, h: 0.95, fontSize: 13, color: BODY, fontFace: BODYF,
});

s.addShape(pres.ShapeType.roundRect, {
  x: 8.15, y: 4.1, w: 4.45, h: 1.95, rectRadius: 0.12,
  fill: { color: "FDF6E3" }, line: { color: "E8D9A8", width: 1 },
});
s.addText("The lever we rejected", { x: 8.35, y: 4.28, w: 4.05, h: 0.3, fontSize: 11, bold: true, color: AMBER, fontFace: BODYF, charSpacing: 1 });
s.addText(
  `"More titles per order" showed a ${titles.uplift_pp.toFixed(0)}pp gap — the biggest in the data. Its coefficient collapses +${MD.cds_coef_alone.toFixed(2)} → +${MD.cds_coef_joint.toFixed(2)} once basket value is controlled.`,
  { x: 8.35, y: 4.6, w: 4.05, h: 1.3, fontSize: 12.5, color: INK, fontFace: BODYF }
);
s.addNotes(`Basket value and title count correlate ${MD.corr_value_cds.toFixed(2)}. Customers who buy three titles return because they spent more, not because they bought more items. Acting on the raw gap pushes merchandising toward cheap add-ons.`);

// ── 4. Recommendation ───────────────────────────────────────────────────────
s = pres.addSlide();
s.background = { color: WHITE };
s.addText("Recommendation", { x: 0.7, y: 0.55, w: 9, h: 0.6, fontSize: 40, bold: true, color: INK, fontFace: HEAD });
s.addText("Build the treatment, not the model.", {
  x: 0.7, y: 1.25, w: 11, h: 0.45, fontSize: 19, bold: true, color: NAVY, fontFace: BODYF,
});
s.addText(
  `The model cannot say who will return (AUC ${MD.auc.toFixed(3)} against a ${MD.base_rate.toFixed(3)} base rate), so targeting has nothing to target on. The window is short and known, so a timed treatment does. Ship a second-purchase program to every first-time buyer at day 30 / 55 / 80, weighted to higher-value titles.`,
  { x: 0.7, y: 1.8, w: 11.9, h: 0.95, fontSize: 15, color: BODY, fontFace: BODYF }
);

const R = (lever, o, verdict, vopt) => ([
  lever,
  { text: o.customers.toLocaleString(), options: { align: "right" } },
  { text: k(o.annual_value), options: { align: "right" } },
  { text: o.effort, options: { align: "center" } },
  vopt ? { text: verdict, options: vopt } : verdict,
]);
const rows = [
  [{ text: "Lever", options: { bold: true } },
   { text: "Population", options: { bold: true, align: "right" } },
   { text: "Impact", options: { bold: true, align: "right" } },
   { text: "Effort", options: { bold: true, align: "center" } },
   { text: "Verdict", options: { bold: true } }],
  R("Timed second-purchase nudge", nudge, "Recommended"),
  R("Lift bottom-quartile first baskets", basket, "Recommended"),
  R("More titles in the first order", titles, "Rejected — confounded", { color: AMBER, bold: true }),
  R("Fix the weakest acquisition month", cohort, "Too small to chase"),
];
s.addTable(rows, {
  x: 0.7, y: 3.0, w: 11.9, colW: [4.5, 1.9, 1.6, 1.2, 2.7],
  fontSize: 13, fontFace: BODYF, color: INK,
  border: { type: "solid", color: LINE, pt: 1 },
  fill: { color: WHITE }, rowH: 0.5, valign: "middle",
});
s.addText(
  "Highest impact and lowest effort are the same row. The rejected row carries the second-largest number — ranking by size alone would have picked it, which is why the control step exists.",
  { x: 0.7, y: 5.95, w: 11.9, h: 0.7, fontSize: 14, italic: true, color: INK, fontFace: BODYF }
);
s.addNotes("Both dollar figures are deliberately conservative: 25% capture on the basket lever, and the 3pp lift on the nudge is assumed rather than measured.");

// ── 5. How we'd know (dark close) ───────────────────────────────────────────
s = pres.addSlide();
s.background = { color: NAVY };
s.addText("How we'd know it worked", { x: 0.8, y: 0.7, w: 10, h: 0.7, fontSize: 40, bold: true, color: WHITE, fontFace: HEAD });

const cards = [
  ["Primary metric", "180-day repeat rate, treatment vs. a permanent holdout."],
  ["Ship / kill", "Ship at ≥2pp lift (p<0.05) after one full cohort. Kill below 1pp."],
  ["Counter-metric", "Value of the second order. A lift bought by discounting is not a win."],
];
cards.forEach(([t, b], i) => {
  const x = 0.8 + i * 4.05;
  s.addShape(pres.ShapeType.roundRect, {
    x, y: 1.95, w: 3.7, h: 2.5, rectRadius: 0.12,
    fill: { color: "2A3A72" }, line: { color: "3A4A85", width: 1 },
  });
  s.addText(t, { x: x + 0.25, y: 2.15, w: 3.2, h: 0.35, fontSize: 15, bold: true, color: ICE, fontFace: BODYF, valign: "top", margin: 0 });
  s.addText(b, { x: x + 0.25, y: 2.6, w: 3.2, h: 1.7, fontSize: 13, color: WHITE, fontFace: BODYF, valign: "top", margin: 0 });
});

s.addText("What would change my mind", { x: 0.8, y: 5.05, w: 10, h: 0.4, fontSize: 15, bold: true, color: ICE, fontFace: BODYF });
s.addText(
  "If the holdout shows under 1pp after a full cohort, the window hypothesis is wrong and the constraint is more likely product selection than timing. The next investigation would be first-basket composition, not lifecycle timing.",
  { x: 0.8, y: 5.45, w: 11.7, h: 0.9, fontSize: 14, color: "C8D4F0", fontFace: BODYF }
);
s.addText("The 3pp lift is assumed, not measured. The holdout exists to prove or kill it.", {
  x: 0.8, y: 6.6, w: 11.7, h: 0.4, fontSize: 12.5, italic: true, color: "8FA4D8", fontFace: BODYF,
});
s.addNotes("Pre-committing to a kill threshold is the point. An analysis that cannot be wrong is not worth running.");

pres.writeFile({ fileName: "/home/user/ecommerce-customer-retention-analysis/docs/cdnow-retention-executive-deck.pptx" })
  .then(f => console.log("wrote", f));
