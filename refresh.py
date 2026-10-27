#!/usr/bin/env python3
"""Refresh the AIPAC tracker and rebuild the page.

    python refresh.py api            # daily path, needs FEC_API_KEY
    python refresh.py bulk           # fallback, no key, big download
    python refresh.py build          # rebuild the page from data/ only

The API path makes about 35 calls. The bulk path downloads the official
committee files (pas2, oth, cm, cn) and parses them locally.
"""
import argparse
import io
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import date

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data"
sys.path.insert(0, str(HERE))
FEC = "https://api.open.fec.gov/v1"
UA = "aipac-money-tracker/1.0 (research; contact: site owner)"
TODAY = date.today().isoformat()

UDP = "C00799031"
AIPAC_PAC = "C00797670"
NONPROFITS = {"AIPAC_C4": "530217164", "AIEF_C3": "521623781"}
KEEP_FROM_OLD_SEED = ("announcement", "reported_figures")

API_KEY = os.environ.get("FEC_API_KEY", "").strip()


# ---------------------------------------------------------------- transport
def http_json(url, tries=4):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < tries - 1:
                wait = 20 * (attempt + 1)
                print(f"  rate limited, waiting {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"failed: {url}")


def fec(path, **params):
    params["api_key"] = API_KEY
    url = f"{FEC}{path}?{urllib.parse.urlencode(params)}"
    return http_json(url)


def paged(path, **params):
    page = 1
    while True:
        d = fec(path, page=page, per_page=100, **params)
        for row in d.get("results", []):
            yield row
        pages = d.get("pagination", {}).get("pages", 1)
        if page >= pages:
            break
        page += 1
        time.sleep(0.2)


def need_key():
    if not API_KEY:
        raise SystemExit(
            "No FEC API key. Set FEC_API_KEY, or use `python refresh.py bulk`.\n"
            "Free key: https://api.data.gov/signup/ (one minute, no cost).")


# ------------------------------------------------------------------ helpers
def num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def day(v):
    return str(v or "")[:10]


def iso_date(v):
    """MMDDYYYY (bulk) or ISO (API) -> ISO."""
    d = str(v or "")
    if len(d) == 8 and d.isdigit():
        return f"{d[4:]}-{d[:2]}-{d[2:4]}"
    return d[:10]


def fetch_nonprofits():
    out = {}
    names = {"AIPAC_C4": ("American Israel Public Affairs Committee", "53-0217164",
                          "501(c)(4) social welfare organization", "none"),
             "AIEF_C3": ("American Israel Education Foundation Inc", "52-1623781",
                         "501(c)(3) charity", "none (Schedule B confidential)")}
    for key, ein in NONPROFITS.items():
        try:
            d = http_json(f"https://projects.propublica.org/nonprofits/api/v2/organizations/{ein}.json")
        except Exception as e:
            print(f"  nonprofit {key} unavailable ({e}); keeping previous figures", file=sys.stderr)
            out[key] = None
            continue
        hist = sorted([{
            "year": f["tax_prd_yr"],
            "revenue": f["totrevenue"],
            "expenses": f["totfuncexpns"],
            "assets": f["totassetsend"],
        } for f in d.get("filings_with_data", [])], key=lambda x: x["year"])
        org = d["organization"]
        out[key] = {
            "name": org["name"],
            "ein": ein,
            "status": names[key][2],
            "donor_disclosure": names[key][3],
            "history": hist,
            "revenue_total": sum(h["revenue"] for h in hist),
            "url": f"https://projects.propublica.org/nonprofits/organizations/{ein}",
        }
    return out


def committee_summary(cid, cycle):
    t = fec(f"/committee/{cid}/totals/", cycle=cycle)["results"][0]
    return {
        "id": cid,
        "name": t.get("committee_name"),
        "kind": t.get("committee_type_full"),
        "cycle": cycle,
        "receipts": num(t.get("receipts")),
        "individual": num(t.get("individual_contributions")),
        "disbursements": num(t.get("disbursements")),
        "independent_expenditures": num(t.get("independent_expenditures")),
        "cash_on_hand": num(t.get("last_cash_on_hand_end_period") or t.get("cash_on_hand_end_period")),
        "committee_transfers": num(t.get("fed_candidate_committee_contributions")),
        "coverage_end": day(t.get("coverage_end_date")),
        "url": f"https://www.fec.gov/data/committee/{cid}/",
    }


def committee_transfers(cycle):
    """UDP's outbound committee-to-committee transfers, from Schedule B."""
    agg = {}
    for r in paged("/schedules/schedule_b/", committee_id=UDP, cycle=cycle):
        rid = str(r.get("recipient_committee_id") or r.get("other_id") or "")
        if not rid.startswith("C"):
            continue
        amt = num(r.get("disbursement_amount"))
        d = day(r.get("disbursement_date"))
        cur = agg.setdefault(rid, {"name": r.get("recipient_name") or rid,
                                   "amount": 0.0, "transfers": 0, "first": "9999-99-99"})
        cur["amount"] += amt
        cur["transfers"] += 1
        if d:
            cur["first"] = min(cur["first"], d)
    if not agg:
        raise RuntimeError(
            "Schedule B returned no committee recipients. The field names may have "
            "changed; check one record before letting the job overwrite data.")
    return agg


def committee_spending(cid, cycle):
    """A committee's own independent spending this cycle."""
    total, n, first, last = 0.0, 0, "", ""
    for r in paged("/schedules/schedule_e/", committee_id=cid, cycle=cycle):
        total += num(r.get("expenditure_amount"))
        n += 1
        d = day(r.get("expenditure_date"))
        if d:
            first = min(first or d, d)
            last = max(last or d, d)
    return round(total, 2), n, first, last


def independent_expenditures(cycle):
    agg = {}
    for r in paged("/schedules/schedule_e/", committee_id=UDP, cycle=cycle):
        cid = str(r.get("candidate_id") or "")
        if not cid.startswith(("H", "S")):
            continue
        side = "support" if r.get("support_oppose_indicator") == "S" else "oppose"
        key = (cid, side)
        cur = agg.setdefault(key, {
            "candidate_id": cid,
            "name": (f"{r.get('candidate_last_name')}, {r.get('candidate_first_name')}"
                     if r.get("candidate_last_name") else (r.get("candidate_name") or cid)),
            "office": {"H": "House", "S": "Senate"}.get(r.get("candidate_office"), r.get("candidate_office")),
            "state": r.get("candidate_office_state"),
            "district": str(r.get("candidate_office_district") or "").lstrip("0"),
            "side": side,
            "amount": 0.0,
        })
        cur["amount"] += num(r.get("expenditure_amount"))
    out = list(agg.values())
    for x in out:
        x["amount"] = round(x["amount"], 2)
    return sorted(out, key=lambda x: -x["amount"])


def pac_gifts(cycle):
    total, rows = 0.0, []
    for r in paged("/schedules/schedule_b/by_recipient/", committee_id=AIPAC_PAC, cycle=cycle):
        amt = num(r.get("total"))
        total += amt
        rows.append({"committee": r.get("recipient_name"), "amount": round(amt, 2)})
    return rows, round(total, 2)


# --------------------------------------------------------------------- api
def collect_api(cycle):
    need_key()
    print("FEC API: totals", flush=True)
    udp = committee_summary(UDP, cycle)
    pac = committee_summary(AIPAC_PAC, cycle)

    print("FEC API: UDP committee transfers", flush=True)
    transfers = committee_transfers(cycle)

    conduits = []
    for i, (cid, t) in enumerate(sorted(transfers.items(), key=lambda kv: -kv[1]["amount"]), 1):
        print(f"  conduit {i}/{len(transfers)}: {t['name']}", flush=True)
        info = {}
        try:
            info = fec(f"/committee/{cid}/", cycle=cycle)["results"][0]
        except Exception:
            pass
        spent, n, first_spend, last_spend = committee_spending(cid, cycle)
        conduits.append({
            "id": cid,
            "name": t["name"],
            "amount": round(t["amount"], 2),
            "transfers": t["transfers"],
            "first_seen": t["first"] if t["first"] != "9999-99-99" else None,
            "kind": info.get("committee_type_full"),
            "connected": info.get("connected_org_name") or None,
            "source": "FEC Schedule B",
            "spent": spent,
            "spend_txns": n,
            "first_spend": first_spend,
            "last_spend": last_spend,
        })

    print("FEC API: independent expenditures", flush=True)
    ies = independent_expenditures(cycle)

    print("FEC API: AIPAC PAC gifts", flush=True)
    gifts, gift_total = pac_gifts(cycle)

    print("Nonprofit filings: ProPublica", flush=True)
    nonprofits = fetch_nonprofits()

    seed, derived = assemble(udp, pac, nonprofits, ies, gifts, gift_total, conduits)
    return seed, derived


# -------------------------------------------------------------------- bulk
def resolve(url):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.geturl(), int(r.headers.get("Content-Length") or 0)


def download_zip(url, dest):
    final, total = resolve(url)
    if total <= 0:
        raise RuntimeError(f"no content length: {url}")
    if dest.exists() and dest.stat().st_size == total:
        try:
            if zipfile.ZipFile(dest).testzip() is None:
                print(f"  cached {dest.name}", flush=True)
                return
        except zipfile.BadZipFile:
            pass
    print(f"  downloading {dest.name} ({total/1e6:.0f} MB)", flush=True)
    n = 8
    chunk = (total + n - 1) // n
    parts = []
    for i in range(n):
        start = i * chunk
        end = min(total - 1, start + chunk - 1)
        want = end - start + 1
        for attempt in range(4):
            req = urllib.request.Request(final, headers={"User-Agent": UA,
                                                         "Range": f"bytes={start}-{end}"})
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    data = r.read()
            except Exception:
                data = b""
            if len(data) == want:
                parts.append(data)
                break
        else:
            raise RuntimeError(f"chunk {i} failed for {dest.name}")
    with open(dest, "wb") as f:
        for p in parts:
            f.write(p)
    if zipfile.ZipFile(dest).testzip() is not None:
        raise RuntimeError(f"corrupt zip: {dest.name}")


def collect_bulk(cycle, download=True):
    yy = str(cycle)[-2:]
    files = {"pas2": f"pas2{yy}.zip", "oth": f"oth{yy}.zip",
             "cm": f"cm{yy}.zip", "cn": f"cn{yy}.zip"}
    if download:
        for name, fn in files.items():
            download_zip(f"https://www.fec.gov/files/bulk-downloads/{cycle}/{fn}", DATA / fn)

    os.environ["FEC_CYCLE"] = str(cycle)
    import parse_bulk

    # Bulk files carry transfers and spending, not committee totals. Keep the
    # totals from the last API run (or the original research seed) rather than
    # replacing them with older figures; only build the seed from scratch if
    # none exists.
    if not (DATA / "seed.json").exists():
        import make_seed
        make_seed.main()

    parse_bulk.main()

    seed = json.loads((DATA / "seed.json").read_text(encoding="utf-8"))
    derived = json.loads((DATA / "derived.json").read_text(encoding="utf-8"))
    seed["built_at"] = TODAY
    return seed, derived


# ----------------------------------------------------------------- assemble
def assemble(udp, pac, nonprofits, ies, gifts, gift_total, conduits):
    old = {}
    path = DATA / "seed.json"
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))

    seed = {k: old.get(k) for k in KEEP_FROM_OLD_SEED if old.get(k)}
    seed.update({
        "built_at": TODAY,
        "coverage_end": udp["coverage_end"] or pac["coverage_end"],
        "committees": {"UDP": udp, "AIPAC_PAC": pac},
    })
    if nonprofits:
        seed["nonprofit"] = {k: v for k, v in nonprofits.items() if v}
    elif old.get("nonprofit"):
        seed["nonprofit"] = old["nonprofit"]

    derived = {
        "conduits": conduits,
        "conduit_total": round(sum(c["amount"] for c in conduits), 2),
        "independent_expenditures": ies,
        "ie_total": round(sum(x["amount"] for x in ies), 2),
        "aipac_pac_candidate_gifts": gifts,
        "aipac_pac_gift_total": gift_total,
    }
    return seed, derived


def write(seed, derived):
    DATA.mkdir(exist_ok=True)
    (DATA / "seed.json").write_text(json.dumps(seed, indent=1), encoding="utf-8")
    (DATA / "derived.json").write_text(json.dumps(derived, indent=1), encoding="utf-8")
    udp = seed["committees"]["UDP"]
    line = (f"UDP raised ${udp['receipts']:,.0f}; ads ${derived['ie_total']:,.0f}; "
            f"{len(derived['conduits'])} middleman PACs, ${derived['conduit_total']:,.0f}; "
            f"filings through {seed['coverage_end']}")
    (DATA / "last_refresh.txt").write_text(line + "\n", encoding="utf-8")
    print(line)
    print(f"wrote seed.json and derived.json "
          f"({len(derived['conduits'])} middlemen, {len(derived['independent_expenditures'])} candidates)")


def doctor(cycle):
    """Pre-flight: check the key, the endpoints and the field shapes."""
    ok = True
    print(f"python {sys.version.split()[0]}")
    print(f"cycle {cycle}")

    if not API_KEY:
        print("FAIL  FEC_API_KEY is not set")
        return 1

    for label, path, params in [
        ("committee totals", f"/committee/{UDP}/totals/", {"cycle": cycle}),
        ("Schedule B (transfers)", "/schedules/schedule_b/", {"committee_id": UDP, "cycle": cycle, "per_page": 5}),
        ("Schedule E (spending)", "/schedules/schedule_e/", {"committee_id": UDP, "cycle": cycle, "per_page": 5}),
    ]:
        try:
            d = fec(path, **params)
            rows = d.get("results", [])
            print(f"PASS  {label}: {len(rows)} rows")
            if label.startswith("Schedule B") and rows:
                sample = rows[0]
                has_id = bool(sample.get("recipient_committee_id") or sample.get("other_id"))
                has_amt = "disbursement_amount" in sample
                print(f"      sample keys: recipient id {'yes' if has_id else 'NO'}, amount {'yes' if has_amt else 'NO'}")
                if not (has_id and has_amt):
                    ok = False
                    print("      FAIL  expected fields missing; send this line to whoever maintains the script")
        except Exception as e:
            ok = False
            print(f"FAIL  {label}: {e}")

    try:
        d = http_json(f"https://projects.propublica.org/nonprofits/api/v2/organizations/{NONPROFITS['AIPAC_C4']}.json")
        print(f"PASS  ProPublica: {len(d.get('filings_with_data', []))} filings")
    except Exception as e:
        ok = False
        print(f"FAIL  ProPublica: {e}")

    print("READY" if ok else "NOT READY")
    return 0 if ok else 1


def summary(seed, derived):
    udp = seed["committees"]["UDP"]
    return (f"UDP raised ${udp['receipts']:,.0f}; ads ${derived['ie_total']:,.0f}; "
            f"{len(derived['conduits'])} middleman PACs, ${derived['conduit_total']:,.0f}; "
            f"filings through {seed['coverage_end']}")


def compare(old_seed, old_derived, seed, derived):
    def d(a, b, label, fmt="${:,.0f}"):
        if abs(a - b) > 0.5:
            print(f"  {label}: {fmt.format(b)} -> {fmt.format(a)}")
    d(seed["committees"]["UDP"]["receipts"], old_seed["committees"]["UDP"]["receipts"], "UDP raised")
    d(derived["ie_total"], old_derived.get("ie_total", 0), "UDP on ads")
    d(derived["conduit_total"], old_derived.get("conduit_total", 0), "Middleman transfers")
    if len(derived["conduits"]) != len(old_derived.get("conduits", [])):
        print(f"  Middlemen: {len(old_derived.get('conduits', []))} -> {len(derived['conduits'])}")


def main():
    global API_KEY
    ap = argparse.ArgumentParser()
    ap.add_argument("source", choices=["api", "bulk", "build", "doctor"], nargs="?", default="api")
    ap.add_argument("--cycle", type=int, default=0)
    ap.add_argument("--key", default="")
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="collect and report, write nothing")
    args = ap.parse_args()

    if args.key:
        API_KEY = args.key.strip()

    cycle = args.cycle or (date.today().year if date.today().year % 2 == 0 else date.today().year + 1)

    if args.source == "build":
        import build_site
        build_site.main()
        return

    if args.source == "doctor":
        sys.exit(doctor(cycle))

    if args.dry_run and args.source == "bulk":
        raise SystemExit("dry run is only available for api; bulk parsing writes data/derived.json")

    if args.source == "api":
        seed, derived = collect_api(cycle)
    else:
        seed, derived = collect_bulk(cycle, download=not args.no_download)

    if args.dry_run:
        print("DRY RUN - nothing written")
        print(summary(seed, derived))
        if (DATA / "seed.json").exists() and (DATA / "derived.json").exists():
            print("Changes against the current data:")
            compare(json.loads((DATA / "seed.json").read_text(encoding="utf-8")),
                    json.loads((DATA / "derived.json").read_text(encoding="utf-8")),
                    seed, derived)
        return

    write(seed, derived)

    # The shared research database only exists on the original machine.
    if (HERE.parent / "DATABASES" / "db.py").exists():
        import ingest
        ingest.main()
    else:
        print("shared database not present; skipping ingest")

    import build_site
    build_site.main()


if __name__ == "__main__":
    main()
