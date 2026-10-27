# Start here

You have one self-contained page and the code that keeps it current. Viewing the
page needs no server, database or key.

## The ten-minute path

1. Create a repository and push this folder.
2. Get a free FEC key at https://api.data.gov/signup/ (one minute, no cost).
   In the repo: Settings > Secrets and variables > Actions > New repository
   secret, named `FEC_API_KEY`.
3. Settings > Pages > deploy from branch, root. The page is then at
   `https://<owner>.github.io/<repo>/AIPAC-Money-Tracker.html`.

The included workflow runs daily at 11:00 UTC and commits the rebuilt page only
when a number or a row changed. Nothing else is required.

## Before the first scheduled run

```
python refresh.py doctor
```

It checks Python, the key, the three FEC endpoints and ProPublica, and prints a
sample record for the transfer data. Finish on `READY`.

To see what a refresh would change without writing anything:

```
python refresh.py api --dry-run
```

## If you are not on GitHub

Run this from cron with the key in the environment, then copy the file to your
web root:

```
0 11 * * * cd /srv/aipac && python3 refresh.py api && cp AIPAC-Money-Tracker.html /var/www/
```

Keep the key out of the crontab; put it in the unit's environment or a secrets
file.

## If something fails

| Message | Meaning |
|---|---|
| `FEC_API_KEY is not set` | Add the secret, or pass `--key`. |
| `rate limited` | Wrong or shared key. A personal key allows 1,000 calls an hour. |
| `Schedule B returned no committee recipients` | The FEC changed a field name. Run `doctor` and send its output. |
| `ProPublica unavailable` | The 990 figures keep their previous values; the rest updates. |

The job is deliberately loud. It stops rather than publish an empty section.

## What updates, and what cannot

Daily: FEC totals, transfers to middleman PACs, independent spending, direct
gifts, coverage dates. New PACs and races appear on their own.

Yearly: IRS 990 figures for AIPAC's 501(c)(4) and the AIEF.

Never: the names of 501(c)(4) donors. They are not public in any filing.

## Files

| File | Use |
|---|---|
| `AIPAC-Money-Tracker.html` | The page to serve. |
| `handover/` | The page plus integration notes, for a CMS team. |
| `refresh.py` | `api`, `bulk`, `build`, `doctor`. |
| `site/template.html` | Page source. Edit this, then `python refresh.py build`. |
| `data/` | Seed and derived JSON. Committed; the large FEC zips are not. |
| `.github/workflows/refresh.yml` | The daily job. |
| `LICENSE` | MIT. Keep the notice if you republish. |

## Editing the page

Colours and type are CSS variables at the top of `site/template.html`. After any
edit run `python refresh.py build`, which writes both HTML files.
