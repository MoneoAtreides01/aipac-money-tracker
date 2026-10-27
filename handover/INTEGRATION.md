# AIPAC Money Tracker - integration notes

A single self-contained page: HTML, CSS, JavaScript and the dataset inlined. No
build step, no package manager, no server-side code, no analytics, no cookies.

## What is in this folder

| File | Purpose |
|---|---|
| `index.html` | The tracker. Serve it and you are done. |
| `data.json` | Every figure on the page, with sources, for reuse elsewhere. |
| `embed-example.html` | A minimal host page showing the iframe below working. |
| `INTEGRATION.md` | This file. |

## Option A - iframe (recommended)

Copy `index.html` anywhere on your server and embed it:

```html
<iframe
  src="/path/to/aipac-money-tracker.html"
  title="AIPAC Money Tracker"
  loading="lazy"
  style="width:100%;height:1500px;border:0;display:block"
></iframe>
```

The iframe keeps the page's styles and element IDs from colliding with your
site's. Recommended heights: 1500px on desktop, 2400px on phones. Add a media
query or a small resize listener if your layout changes a lot.

## Option B - paste into a template

All content sits inside a single `<main class="wrap">`, so it can be pasted into
an article template if you drop the outer `<html>`, `<head>` and `<body>` tags
and move the `<style>` and `<script>` blocks with it. The page has its own sticky
header and footer; remove `<header class="topbar">` and `<footer>` if the host
site already provides navigation. Check for ID collisions: the page uses
`stats`, `doors-grid`, `ledger-body`, `conduit-body`, `bars`, `sync-btn`.

## Option C - data only

`data.json` is the merged dataset used to render the page:

```
seed.announcement              the 21 Oct 2026 letter, quote and framing
seed.committees.UDP            FEC totals, 2026 cycle
seed.committees.AIPAC_PAC      FEC totals, 2026 cycle
seed.nonprofit.AIPAC_C4        IRS 990 history 2011-2023, EIN 53-0217164
seed.nonprofit.AIEF_C3         IRS 990 history 2011-2023, EIN 52-1623781
derived.independent_expenditures   UDP spending by candidate
derived.conduits               committee-to-committee transfers, with amounts
```

All money values are US dollars. Dates are ISO where the source allows.

## Refreshing the figures

The page is static. It contains no refresh code and makes no network requests,
so it works anywhere and needs no API key at view time.

To update it, run the pipeline and replace the file:

```bash
python refresh.py api    # needs FEC_API_KEY; about 35 calls, seconds
python refresh.py bulk   # no key; downloads about 225 MB, minutes
python refresh.py build  # rebuild only, from the data already in data/
```

`refresh.py api` writes `AIPAC-Money-Tracker.html` and `site/index.html`. Copy
either over the file you are serving. The repo includes a GitHub Actions job
that does this daily and commits only when a number changed, so if they can run
it from a repository, no manual step is needed. See `README.md`.

The page loads fonts from Google Fonts. If that is blocked, the local fallback
stacks apply and nothing breaks:

```
font-src  https://fonts.gstatic.com;
style-src https://fonts.googleapis.com 'unsafe-inline';
```

## Editorial notes to keep with the page

- Every figure carries its coverage period. Committee totals are through
  14 October 2026; nonprofit figures are FY2023, the latest 990 on file.
- United Democracy Project and AIPAC PAC disclose their donors. The page says
  so. "Dark money" is used only for the 501(c)(4), the 501(c)(3), and the
  window before a conduit PAC files.
- A conduit PAC is a lawful structure. The page documents where money goes and
  when the public can see it. It does not allege a crime, and that sentence
  should stay in any edited version.
- The page is dated in the footer and the top bar. If you freeze it, update the
  date or remove the Refresh control.

## Styling

Colours, type and spacing are CSS custom properties on `:root` at the top of the
`<style>` block, with dark-mode values in the two dark blocks below. Change
`--accent`, `--blue`, `--paper` and `--ink` to match a host design. The two chart
series colours are `--series-support` and `--series-oppose`; they were validated
for colour-vision deficiency against both themes, so re-check if you change them.

Fonts load from Google Fonts (Newsreader, IBM Plex Sans, IBM Plex Mono) with
local fallback stacks, so the page still reads correctly if the request is
blocked.
