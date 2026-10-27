#!/usr/bin/env python3
"""Write the AIPAC network into the shared research database.

Dataset key: fec_aipac_network
Tables:      aipac_entities, aipac_filings, aipac_transfers,
             aipac_spending, aipac_sources

Idempotent: rows for this dataset are replaced in one transaction. A backup
runs first because the tables are new.
"""
import json
import pathlib
import sys
from datetime import datetime

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "DATABASES"))
from db import backup, connect  # noqa: E402

DATA = HERE / "data"
DATASET = "fec_aipac_network"

SCHEMA = """
CREATE TABLE IF NOT EXISTS aipac_entities (
  dataset TEXT NOT NULL, entity_id TEXT NOT NULL, name TEXT, kind TEXT,
  disclosure TEXT, url TEXT, PRIMARY KEY (dataset, entity_id)
);
CREATE TABLE IF NOT EXISTS aipac_filings (
  dataset TEXT NOT NULL, entity_id TEXT NOT NULL, period_end TEXT NOT NULL,
  raised REAL, spent REAL, cash REAL, assets REAL, source TEXT,
  PRIMARY KEY (dataset, entity_id, period_end)
);
CREATE TABLE IF NOT EXISTS aipac_transfers (
  dataset TEXT NOT NULL, from_committee TEXT NOT NULL, to_committee TEXT,
  to_name TEXT, amount REAL, first_seen TEXT, cycle INTEGER, source TEXT,
  PRIMARY KEY (dataset, from_committee, to_committee, first_seen)
);
CREATE TABLE IF NOT EXISTS aipac_spending (
  dataset TEXT NOT NULL, committee TEXT NOT NULL, candidate_id TEXT NOT NULL,
  candidate TEXT, office TEXT, state TEXT, district TEXT, side TEXT,
  amount REAL, cycle INTEGER, PRIMARY KEY (dataset, committee, candidate_id, side, cycle)
);
CREATE TABLE IF NOT EXISTS aipac_sources (
  dataset TEXT NOT NULL, source_key TEXT NOT NULL, title TEXT, url TEXT,
  retrieved_at TEXT, note TEXT, PRIMARY KEY (dataset, source_key)
);
"""


def load(name):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def main():
    seed, derived = load("seed.json"), load("derived.json")
    if not seed:
        raise SystemExit("run make_seed.py first")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    print("backup:", backup(HERE.parent / "DATABASES" / "israel-palestine" / "backups" /
                            f"events-aipac-{stamp}.sqlite"))
    con = connect()
    con.executescript(SCHEMA)

    with con:
        for t in ("aipac_entities", "aipac_filings", "aipac_transfers",
                  "aipac_spending", "aipac_sources"):
            con.execute(f"DELETE FROM {t} WHERE dataset = ?", (DATASET,))

        ent = []
        for key, c in seed["committees"].items():
            ent.append((DATASET, c["id"], c["name"], c["kind"], "disclosed donors", c["url"]))
        for key, n in seed["nonprofit"].items():
            ent.append((DATASET, n["ein"], n["name"], n["status"], "no donor list", n["url"]))
        con.executemany("INSERT INTO aipac_entities VALUES (?,?,?,?,?,?)", ent)

        filings = []
        for c in seed["committees"].values():
            filings.append((DATASET, c["id"], c["coverage_end"], c["receipts"],
                            c["disbursements"], c["cash_on_hand"], None, c["url"]))
        for n in seed["nonprofit"].values():
            last = n["history"][-1]
            filings.append((DATASET, n["ein"], f"FY{last['year']}", last["revenue"],
                            last["expenses"], None, last["assets"], n["url"]))
        con.executemany("INSERT INTO aipac_filings VALUES (?,?,?,?,?,?,?,?)", filings)

        transfers = [
            (DATASET, "C00799031", t.get("id"), t["name"], t["amount"],
             t.get("first_seen"), 2026, t.get("source", "FEC oth26.zip"))
            for t in derived.get("conduits", [])
        ]
        if transfers:
            con.executemany("INSERT INTO aipac_transfers VALUES (?,?,?,?,?,?,?,?)", transfers)

        spending = [
            (DATASET, "C00799031", x["candidate_id"], x["name"], x["office"],
             x["state"], x["district"], x["side"], x["amount"], 2026)
            for x in derived.get("independent_expenditures", [])
        ]
        con.executemany("INSERT INTO aipac_spending VALUES (?,?,?,?,?,?,?,?,?,?)", spending)

        con.execute("INSERT INTO aipac_sources VALUES (?,?,?,?,?,?)", (
            DATASET, "fec_openfec", "FEC OpenFEC API",
            "https://api.open.fec.gov", "2026-10-27",
            "Committee totals and Schedule B; coverage through 2026-10-14"))
        con.execute("INSERT INTO aipac_sources VALUES (?,?,?,?,?,?)", (
            DATASET, "fec_bulk_2026", "FEC bulk files, 2025-2026 cycle",
            "https://www.fec.gov/data/browse-data/?tab=bulk-data", "2026-10-27",
            "pas226.zip (contributions and other expenditures), oth26.zip (committee transfers)"))
        con.execute("INSERT INTO aipac_sources VALUES (?,?,?,?,?,?)", (
            DATASET, "irs_990", "IRS Form 990 via ProPublica Nonprofit Explorer",
            "https://projects.propublica.org/nonprofits/", "2026-10-27",
            "AIPAC 53-0217164 and AIEF 52-1623781, FY2011-2023"))

    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t} WHERE dataset=?", (DATASET,)).fetchone()[0]
              for t in ("aipac_entities", "aipac_filings", "aipac_transfers",
                        "aipac_spending", "aipac_sources")}
    con.close()
    print("ingested:", counts)


if __name__ == "__main__":
    main()
