#!/usr/bin/env python3
"""Build data/seed.json from the figures verified during the 2026-10-27 research pass.

FEC totals come from /committee/{id}/totals/ (coverage through 2026-10-14).
Nonprofit history comes from ProPublica Nonprofit Explorer (IRS 990 extracts).
"""
import json
import pathlib

DATA = pathlib.Path(__file__).resolve().parent / "data"


def load_pp(name):
    d = json.loads((DATA / name).read_text(encoding="utf-8"))
    hist = [{
        "year": f["tax_prd_yr"],
        "revenue": f["totrevenue"],
        "expenses": f["totfuncexpns"],
        "assets": f["totassetsend"],
    } for f in d["filings_with_data"]]
    hist.sort(key=lambda x: x["year"])
    return d["organization"], hist


def main():
    aipac_org, aipac_hist = load_pp("pp_aipac_c4.json")
    aief_org, aief_hist = load_pp("pp_aief_c3.json")

    seed = {
        "built_at": "2026-10-27",
        "coverage_end": "2026-10-14",
        "announcement": {
            "date": "2026-10-21",
            "quote": "Endorsements, direct PAC contributions, and earmarking will no longer be part of our approach.",
            "framing": "a more strategic, consequential, and nimble political operation",
            "continuation": "Mobilizing greater resources for AIPAC, pro-Israel candidates and our super PAC is critical.",
            "source": "AIPAC email to supporters, reported by Middle East Eye, The Guardian and Jewish Insider",
            "url": "https://www.middleeasteye.net/news/pro-israel-lobbying-group-aipac-ends-endorsements-direct-funding-us-candidates",
        },
        "committees": {
            "UDP": {
                "id": "C00799031",
                "name": "United Democracy Project",
                "kind": "Super PAC (independent expenditure only)",
                "cycle": 2026,
                "receipts": 112820861.12,
                "individual": 108557590.22,
                "disbursements": 85057423.26,
                "independent_expenditures": 53603927.44,
                "cash_on_hand": 56656632.96,
                "committee_transfers": 13131200.00,
                "coverage_end": "2026-10-14",
                "url": "https://www.fec.gov/data/committee/C00799031/",
            },
            "AIPAC_PAC": {
                "id": "C00797670",
                "name": "American Israel Public Affairs Committee PAC",
                "kind": "Qualified PAC",
                "cycle": 2026,
                "receipts": 57771930.54,
                "individual": 54915730.01,
                "disbursements": 56248372.98,
                "independent_expenditures": 0.0,
                "cash_on_hand": 2551164.34,
                "committee_transfers": 53289529.53,
                "coverage_end": "2026-10-14",
                "url": "https://www.fec.gov/data/committee/C00797670/",
            },
        },
        "nonprofit": {
            "AIPAC_C4": {
                "name": aipac_org["name"],
                "ein": "53-0217164",
                "status": "501(c)(4) social welfare organisation",
                "donor_disclosure": "none",
                "history": aipac_hist,
                "revenue_total": sum(h["revenue"] for h in aipac_hist),
                "url": "https://projects.propublica.org/nonprofits/organizations/530217164",
            },
            "AIEF_C3": {
                "name": aief_org["name"],
                "ein": "52-1623781",
                "status": "501(c)(3) charity",
                "donor_disclosure": "none (Schedule B confidential)",
                "history": aief_hist,
                "revenue_total": sum(h["revenue"] for h in aief_hist),
                "url": "https://projects.propublica.org/nonprofits/organizations/521623781",
            },
        },
        "reported_figures": {
            "members_direct_2026": 90000000,
            "udp_2024_raised": 87100000,
            "udp_2026_spent_primary_note": "about 40% of primary spending routed through conduit PACs, per Politico reporting cited by FactCheck.org",
        },
    }

    (DATA / "seed.json").write_text(json.dumps(seed, indent=1), encoding="utf-8")
    for k, v in seed["nonprofit"].items():
        print(k, "years", v["history"][0]["year"], "-", v["history"][-1]["year"],
              "revenue total", f"${v['revenue_total']:,.0f}")
    print("wrote seed.json")


if __name__ == "__main__":
    main()
