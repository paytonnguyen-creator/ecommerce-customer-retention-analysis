# ecommerce-customer-retention-analysis

Work-in-progress e-commerce customer retention analysis using Python, pandas, and scikit-learn to identify repeat-purchase patterns and develop product strategy recommendations.

This repo also hosts my portfolio site.

## Portfolio site

Plain HTML and CSS — no build step, no npm, no framework. Edit a file, commit, push, and it's live.

```
index.html        home page (hero, approach, work, background, contact)
case-study.html   case study template — copy this for each new project
assets/style.css  all styling; colors live in :root at the top
assets/main.js    footer year + sticky nav border. That's it.
```

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

### Before you share the link

- **Résumé** — the hero links to `assets/resume.pdf`, which doesn't exist yet, so that link is currently dead. Export your resume to PDF and drop it there, or delete the link. Before you do: your resume has your phone number on it, and anything on a GitHub Pages site is public and gets scraped. Consider making a web version with the number stripped.
- **Graduation date** — the site says *Expected May 2028*. Your resume says *December 2028*. Pick one; recruiters see both documents.
