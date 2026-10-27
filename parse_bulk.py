#!/usr/bin/env python3
"""Extract the AIPAC network from FEC bulk files.

Reads:
    data/pas2{yy}.zip  contributions to candidates (and other expenditures)
    data/oth{yy}.zip   committee-to-committee transactions  (optional)
    data/cn{yy}.zip    candidate master, for names

Writes:
    data/derived.json
"""
import io
import json
import os
import pathlib
import zipfile
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data"

CYCLE = int(os.environ.get("FEC_CYCLE", "2026"))
YY = str(CYCLE)[-2:]
PAS = f"pas2{YY}.zip"
OTH = f"oth{YY}.zip"
CM = f"cm{YY}.zip"
CN = f"cn{YY}.zip"

UDP = "C00799031"
AIPAC_PAC = "C00797670"

# Fixed column order of the FEC bulk files (no header row).
CMTE, AMNDT, RPT, PGI, IMAGE, TTYPE, ETYPE, NAME, CITY, STATE, ZIP = range(11)
EMPLOYER, OCCUPATION, DATE, AMOUNT, OTHER_ID, TRAN_ID, FILE_NUM = range(11, 18)


def rows(zip_name, member):
    with zipfile.ZipFile(DATA / zip_name) as z:
        with z.open(member) as raw:
            for line in io.TextIOWrapper(raw, encoding="latin-1"):
                yield line.rstrip("\r\n").split("|")


def load_candidates():
    out = {}
    path = DATA / CN
    if not path.exists():
        return out
    with zipfile.ZipFile(path) as z:
        for line in io.TextIOWrapper(z.open("cn.txt"), encoding="latin-1"):
            r = line.rstrip("\r\n").split("|")
            if len(r) > 5:
                out[r[0]] = {"name": r[1], "party": r[2], "state": r[4],
                             "office": {"H": "House", "S": "Senate"}.get(r[5], r[5]),
                             "district": r[6].lstrip("0")}
    return out


COMMITTEE_TYPES = {"O": "Super PAC", "W": "Hybrid PAC", "V": "Hybrid PAC (non-contribution)",
                   "N": "PAC (nonqualified)", "Q": "PAC (qualified)", "U": "Single-candidate IE"}


def committee_master():
    """CMTE_ID -> type and connected organisation, from cm26.zip."""
    out = {}
    path = DATA / CM
    if not path.exists():
        return out
    with zipfile.ZipFile(path) as z:
        for line in io.TextIOWrapper(z.open("cm.txt"), encoding="latin-1"):
            r = line.rstrip("\r\n").split("|")
            if len(r) > 13:
                out[r[0]] = {"kind": COMMITTEE_TYPES.get(r[9], r[9]),
                             "connected": r[13] if r[13] not in ("", "NONE") else None}
    return out


def committee_transfers():
    """Outbound committee-to-committee transfers from UDP, from oth26.zip."""
    path = DATA / OTH
    if not path.exists():
        return []
    master = committee_master()
    agg = {}
    for r in rows(OTH, "itoth.txt"):
        if len(r) < 17 or r[CMTE] != UDP:
            continue
        other = r[OTHER_ID]
        if not other.startswith("C"):
            continue                      # not a committee
        try:
            amt = float(r[AMOUNT] or 0)
        except ValueError:
            continue
        d = r[DATE]
        date = f"{d[4:]}-{d[:2]}-{d[2:4]}" if len(d) == 8 else d
        key = (other, r[NAME])
        cur = agg.setdefault(key, {"amount": 0.0, "count": 0, "first": "9999"})
        cur["amount"] += amt
        cur["count"] += 1
        cur["first"] = min(cur["first"], date)
    out = [{"id": k[0], "name": k[1], "amount": round(v["amount"], 2),
            "transfers": v["count"], "first_seen": v["first"],
            "kind": master.get(k[0], {}).get("kind"),
            "connected": master.get(k[0], {}).get("connected"),
            "source": "FEC oth26.zip"} for k, v in agg.items()]
    return sorted(out, key=lambda x: -x["amount"])


def iso(d):
    return f"{d[4:]}-{d[:2]}-{d[2:4]}" if len(d) == 8 else d


def conduit_activity(ids):
    """Each conduit's own independent spending, from pas226.zip."""
    out = {i: {"spent": 0.0, "spend_txns": 0, "first_spend": "9999", "last_spend": ""}
           for i in ids}
    for r in rows(PAS, "itpas2.txt"):
        if len(r) < 16 or r[CMTE] not in out or r[TTYPE] not in ("24E", "24A"):
            continue
        try:
            amt = float(r[AMOUNT] or 0)
        except ValueError:
            continue
        a = out[r[CMTE]]
        a["spent"] += amt
        a["spend_txns"] += 1
        d = iso(r[DATE])
        a["first_spend"] = min(a["first_spend"], d)
        a["last_spend"] = max(a["last_spend"], d)
    for a in out.values():
        a["spent"] = round(a["spent"], 2)
        if a["first_spend"] == "9999":
            a["first_spend"] = None
    return out


def main():
    cands = load_candidates()
    ie = defaultdict(float)          # (candidate_id, support_oppose, election) -> amount
    aipac_candidates = defaultdict(float)
    udp_vendors = defaultdict(float)

    for r in rows(PAS, "itpas2.txt"):
        if len(r) < 16:
            continue
        cmte, ttype, etype, name, other, amt = (
            r[CMTE], r[TTYPE], r[ETYPE], r[NAME], r[OTHER_ID], r[AMOUNT])
        try:
            amt = float(amt or 0)
        except ValueError:
            continue
        if cmte == UDP and ttype in ("24E", "24A") and other.startswith(("H", "S")):
            ie[(other, "support" if ttype == "24E" else "oppose")] += amt
        elif cmte == UDP and etype == "ORG":
            udp_vendors[name] += amt
        elif cmte == AIPAC_PAC and ttype == "24K" and etype == "CCM":
            aipac_candidates[name] += amt

    ies = []
    for (cid, side), amount in sorted(ie.items(), key=lambda x: -x[1]):
        c = cands.get(cid, {})
        ies.append({
            "candidate_id": cid,
            "name": c.get("name", cid),
            "party": c.get("party"),
            "office": c.get("office"),
            "state": c.get("state"),
            "district": c.get("district"),
            "side": side,
            "amount": round(amount, 2),
        })

    conduits = committee_transfers()
    activity = conduit_activity({c["id"] for c in conduits})
    for c in conduits:
        c.update(activity.get(c["id"], {}))
    out = {
        "conduits": conduits,
        "conduit_total": round(sum(c["amount"] for c in conduits), 2),
        "independent_expenditures": ies,
        "ie_total": round(sum(x["amount"] for x in ies), 2),
        "aipac_pac_candidate_gifts": [
            {"committee": k, "amount": round(v, 2)}
            for k, v in sorted(aipac_candidates.items(), key=lambda x: -x[1])
        ],
        "aipac_pac_gift_total": round(sum(aipac_candidates.values()), 2),
        "udp_vendor_payments": [
            {"vendor": k, "amount": round(v, 2)}
            for k, v in sorted(udp_vendors.items(), key=lambda x: -x[1])[:15]
        ],
    }

    (DATA / "derived.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"IE records: {len(ies)}  total ${out['ie_total']:,.0f}")
    print(f"AIPAC PAC gifts: ${out['aipac_pac_gift_total']:,.0f}")
    print("\nTop IEs:")
    for x in ies[:8]:
        print(f"  {x['side']:7} {x['amount']:>12,.0f}  {x['name']} ({x['party']} {x['state']})")


if __name__ == "__main__":
    main()
