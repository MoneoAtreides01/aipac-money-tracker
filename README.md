# AIPAC Money Tracker

New here? Read `START-HERE.md` first.

Tracks the money behind AIPAC's electoral operation from public filings, and
keeps tracking it after AIPAC's 21 October 2026 announcement that it will stop
endorsing candidates and stop making direct PAC contributions.

## What updates, and when

| Source | Covers | Cadence |
|---|---|---|
| FEC OpenFEC API | Committee totals, Schedule B transfers, independent spending, direct gifts | Filings land overnight; the job runs daily |
| ProPublica Nonprofit Explorer (IRS 990) | AIPAC 501(c)(4), AIEF 501(c)(3) | Once a year, with a lag |
| FEC bulk files | Same data, complete and slower; used as the fallback | Daily file drop |

The page is generated from the data, so a refresh adds new middleman PACs, new
races and new totals with no editing. The job only commits when a number or a
row actually changed, so quiet days leave no noise in the history.

## Daily job (GitHub Actions)

`.github/workflows/refresh.yml` runs at 11:00 UTC (07:00 Eastern in summer,
06:00 in winter), rebuilds the page, and commits the result.

Set it up once:

1. Push this folder to a repository.
2. Get a free FEC key at https://api.data.gov/signup/ (one minute, no cost).
3. Add it as a repository secret named `FEC_API_KEY`
   (Settings > Secrets and variables > Actions).
4. Either host the repo with GitHub Pages, or point an existing static host at
   `AIPAC-Money-Tracker.html` on the main branch. Any host that redeploys on
   commit works.

Run it by hand any time from the Actions tab (`workflow_dispatch`).

## Local commands

```bash
python refresh.py api            # daily path; needs FEC_API_KEY
python refresh.py api --dry-run  # fetch and report, write nothing
python refresh.py bulk           # no key; downloads and parses the bulk files
python refresh.py build          # no network; rebuild the page from data/
python refresh.py doctor         # pre-flight check of key and endpoints
python test_refresh.py           # shape tests for the API path
```

On Windows, `set FEC_API_KEY=...` before the first command.

The bulk path is a manual fallback if the API changes or a key is unavailable.
It downloads about 225 MB and takes several minutes; the API path takes seconds.
It refreshes the transfer and spending tables from the official files but keeps
the committee totals from the last API run, because the bulk files do not carry
them. Run `api` when totals need to move.

## Files

```
refresh.py             collect (API or bulk), write data, rebuild the page
parse_bulk.py          bulk-file parser (cycle-aware, FEC_CYCLE env)
make_seed.py           rebuilds seed.json from the bulk/IRS inputs
ingest.py              optional: writes to the shared research database
build_site.py          injects data into the page
site/template.html     page source, with __DATA__ placeholder
test_refresh.py        API shape tests with canned responses
make_handover.py       builds dist/AIPAC-Money-Tracker-handover.zip
.github/workflows/    daily job
```

Outputs: `AIPAC-Money-Tracker.html` (standalone page) and `site/index.html`
(the same page without the document wrapper, for hosts that supply one).

## What the page shows, and what it cannot

- Committee figures are FEC totals as filed. Coverage dates are printed with
  the numbers; a filing can be amended later.
- The 501(c)(4) and 501(c)(3) publish totals only. Their donor lists are not
  public in any form, so no refresh can reveal them.
- A middleman PAC's own spending is not proof that it spent UDP's money; the
  funds are commingled. The page says this under the table.
- Where the API returns an unexpected shape, the job fails instead of writing
  empty sections. That is deliberate: a red run is better than a silent blank.

## Shared database

`ingest.py` writes to the original research database when it is present at
`../DATABASES/israel-palestine/events.sqlite`, under the dataset key
`fec_aipac_network`. It is skipped automatically on any other machine, so the
repo has no dependency on it.

## Licence

MIT. See `LICENSE`: use it, change it, republish it, including commercially,
provided the copyright notice stays. The quoted statement, linked reporting and
the FEC and IRS data are not covered by this licence and keep their own terms.
