# Open problem: the API refresh does not yet reproduce the verified figures

Read this before touching `refresh.py`. The published page is correct. The
automatic updater is the part that is unfinished.

## Current state

- The live page (`index.html`, `AIPAC-Money-Tracker.html`) shows the last
  verified data, produced by the bulk-file path on 2026-10-27.
- `python refresh.py api` runs, and the daily GitHub Action calls it, but it
  stops at Schedule B before writing. When it fails, it writes nothing, so the
  page is never damaged. That behaviour is intentional.
- `python refresh.py bulk` works and reproduces the page from the FEC bulk
  files. It does not update committee totals (bulk files carry transfers and
  spending, not totals), so it is not the daily path.

## The goal

`python refresh.py api --dry-run` should print a summary that matches the FEC's
own committee totals, then `python refresh.py api` should publish it.

Ground truth, from the FEC totals endpoint, cycle 2026, coverage 2026-10-14:

```text
UDP receipts                 112,820,861
UDP independent expenditures  53,603,927
UDP line 23 (committees)      13,131,200
AIPAC PAC receipts            57,771,931
AIPAC PAC direct gifts         1,870,805   (323 committees, from bulk 24K rows)
```

## What has already been fixed

1. **Pagination.** `/schedules/schedule_b/` and `/schedules/schedule_e/` are
   keyset endpoints. Sending `page=` returns page one every time, which
   multiplied the totals by the page count. `paged()` now follows
   `pagination.last_indexes` and falls back to page numbers for aggregate
   endpoints.
2. **Amended rows.** Schedule E returns each transaction once per amended
   filing, with a new `sub_id` but the same `transaction_id`.
   `latest_by_transaction()` keeps the last version only. This took independent
   spending from $107.6M to $54.0M, against the summary's $53.6M.
3. **Coverage window.** Later filings carry rows dated before the totals'
   coverage end. Itemised rows are cut at `coverage_end` so the page is one
   window.
4. **Earmarks vs gifts.** AIPAC PAC's Schedule B mixes its own capped gifts
   (`disbursement_type` 24K) with member earmarks it transmits (24T). Only 24K
   is counted; if the field is absent the job fails rather than count earmarks.
5. **Server errors.** 500/502/503/504 are retried three times with short waits.
6. **No hangs.** `paged()` refuses after 60 pages, naming the endpoint.

## The remaining failure

`python refresh.py api --dry-run` currently ends with either:

```text
RuntimeError: pagination did not terminate after 60 pages on /schedules/schedule_b/
```

or an `HTTP Error 504: Gateway Timeout` from the same endpoint.

Evidence gathered so far:

- The keyset cursor **does advance** for UDP. Page one ends at
  `last_indexes = {last_disbursement_date: 2026-08-25, last_index: ...595}`;
  requesting again with both values returns an earlier row (COSTCO), not the
  same page.
- A probe of AIPAC PAC's Schedule B at `per_page=5` and `per_page=100` could
  not complete: the FEC returned 504 before a result. So we do not yet know
  whether the 60-page loop is PAC-specific.
- `last_index` alone (without `last_disbursement_date`) is rejected by the API;
  both values are required.
- The FEC API was intermittently returning 502/504 on 2026-10-28, so some
  failures are upstream flakiness, not the code.

## What to try next

1. Reproduce with a key: `python refresh.py api --dry-run`. The stderr prints
   `... N pages` every ten pages, so the failing endpoint is visible.
2. Add a temporary print in `paged()` of `last` before each request and the
   `last_indexes` returned. If the cursor repeats exactly, the endpoint is
   ignoring it; if it advances but rows repeat, dedupe on `sub_id`.
3. Test the PAC endpoint alone at `per_page=25`, `50`, and `100`. A page-size
   sensitivity would explain a loop that appears only on the larger request.
4. Consider using `per_page=50` for Schedule B if 100 is unstable. The FEC
   documents 100 as the maximum, not a guarantee.
5. Keep `validate()` in place. It compares the itemised totals with the FEC
   summary and refuses to publish outside 95%-150% (the window allows late
   filings to add rows). It caught both the earlier double-counting bugs.

## Do not do

- Do not remove the 60-page cap or `validate()` to "make it pass".
- Do not switch back to `page=` for Schedule B/E.
- Do not sum Schedule E without `latest_by_transaction()`.
- Do not count all of AIPAC PAC's Schedule B as gifts; most of it is earmarks.

## Where the code lives

```text
refresh.py   paged()                 keyset vs page pagination
             committee_transfers()   UDP -> committees, line 23
             committee_spending()    a committee's own independent spending
             independent_expenditures()  UDP's spending by candidate
             pac_gifts()             direct gifts only (24K)
             validate()              refuses mismatched totals
             debug()                 prints raw shapes; `python refresh.py debug`
```

`python test_refresh.py` covers the shapes with canned responses, including the
amended-row and earmark cases. It cannot catch live pagination behaviour.

## Useful commands

```bash
python refresh.py doctor          # key, endpoints, sample record
python refresh.py debug           # raw record shapes
python refresh.py api --dry-run   # full collect, writes nothing
python refresh.py bulk            # no key; bulk files, works
python test_refresh.py            # shape tests
```
