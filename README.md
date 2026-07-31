# ecommerce-customer-retention-analysis

Work-in-progress e-commerce customer retention analysis using Python, pandas, and scikit-learn to identify repeat-purchase patterns and develop product strategy recommendations.

This repo also hosts my portfolio site.

## Portfolio site

Plain HTML and CSS — no build step, no npm, no framework. Edit a file, commit, push, and it's live.

There are currently **two designs of the same content**, so they can be compared before picking one:

| | Look |
|---|---|
| `index.html` | Editorial. Light, serif headlines, quiet. Reads like a written argument. |
| `v2.html` | Full-bleed dark hero with portrait and typewriter, 3×3 skills cards, two-column projects. |

Once one wins, rename it to `index.html` and delete the other along with its CSS/JS.

```
index.html        v1 home page
v2.html           v2 home page
case-study.html   case study template — shared by both, copy per project
assets/style.css  v1 styling; colors live in :root at the top
assets/main.js    v1 script (footer year, nav border)
assets/v2.css     v2 styling; colors in :root
assets/v2.js      v2 script (typewriter, scroll-spy, mobile menu)
assets/resume.pdf linked from both
```

### v2 only: adding your photo

The hero circle shows your initials until you add a picture. Save a square headshot as `assets/portrait.jpg`, then in `v2.html` find the `PORTRAIT` comment, uncomment the `<img>` line and delete the `<span>` below it.

### Preview it locally

```bash
python3 -m http.server 8000
```

Then open <http://localhost:8000>.

### Publish it

GitHub repo → **Settings → Pages** → Source: *Deploy from a branch* → Branch: `main`, folder `/ (root)` → Save.

It goes live at `https://paytonnguyen-creator.github.io/ecommerce-customer-retention-analysis/` a minute or two later.

### Adding a project

1. Copy `case-study.html` to something like `retention-v2.html` and rewrite the sections. Keep the section order — question → approach → what the data said → recommendation → what I'd do differently. That order *is* the pitch.
2. In `index.html`, find the `HOW TO ADD A PROJECT` comment in the Selected work section, copy one `<article class="case">` block, and point its links at your new file.
3. Delete the dashed "Planned" placeholder cards once you have real projects.

### Updating the résumé

Replace `assets/resume.pdf` with a new export under the same filename and both links pick it up automatically.

One thing to know: the PDF has your phone number on it, and once Pages is on, that file is publicly reachable and gets scraped by bots. That's a normal tradeoff for a portfolio site — just make it knowingly. If you'd rather not, export a copy with the number removed and use that one here.
