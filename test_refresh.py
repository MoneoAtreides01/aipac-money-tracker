#!/usr/bin/env python3
"""Shape tests for the API path. Run: python -m unittest test_refresh

These use canned responses, not the live API, so they catch field-name and
plumbing mistakes. They cannot prove the live schema still matches; the daily
job fails loudly instead of writing empty data when Schedule B comes back bare.
"""
import unittest
from unittest import mock

import refresh

TOTALS_UDP = {
    "committee_name": "UNITED DEMOCRACY PROJECT ('UDP')",
    "committee_type_full": "Super PAC (Independent Expenditure-Only)",
    "receipts": 112820861.12,
    "individual_contributions": 108557590.22,
    "disbursements": 85057423.26,
    "independent_expenditures": 53603927.44,
    "last_cash_on_hand_end_period": 56656632.96,
    "fed_candidate_committee_contributions": 13131200.0,
    "coverage_end_date": "2026-10-14T00:00:00",
}
TOTALS_PAC = dict(TOTALS_UDP, committee_name="AIPAC PAC", receipts=57771930.54,
                  individual_contributions=54915730.01, disbursements=56248372.98,
                  independent_expenditures=0.0, last_cash_on_hand_end_period=2551164.34)

SCHEDULE_B = [
    {"recipient_committee_id": "C00936724", "recipient_name": "ELECT CHICAGO WOMEN",
     "disbursement_amount": 4011200.0, "disbursement_date": "2026-02-02"},
    {"recipient_committee_id": "C00935049", "recipient_name": "AFFORDABLE CHICAGO NOW!",
     "disbursement_amount": 1320000.0, "disbursement_date": "2026-02-02"},
    {"recipient_committee_id": "", "recipient_name": "TARGETED PLATFORM MEDIA LLC",
     "disbursement_amount": 999.0, "disbursement_date": "2026-02-03"},
]

SCHEDULE_E_UDP = [
    {"candidate_id": "S6MI00426", "candidate_first_name": "HALEY", "candidate_last_name": "STEVENS",
     "candidate_office": "S", "candidate_office_state": "MI", "candidate_office_district": "",
     "support_oppose_indicator": "S", "expenditure_amount": 10517811.0, "expenditure_date": "2026-03-01"},
    {"candidate_id": "S6MI00418", "candidate_first_name": "ABDUL", "candidate_last_name": "EL-SAYED",
     "candidate_office": "S", "candidate_office_state": "MI", "candidate_office_district": "",
     "support_oppose_indicator": "O", "expenditure_amount": 20140901.0, "expenditure_date": "2026-03-02"},
]

SCHEDULE_E_CONDUIT = [
    {"expenditure_amount": 9000000.0, "expenditure_date": "2026-02-04"},
    {"expenditure_amount": 795804.0, "expenditure_date": "2026-03-12"},
]

GIFTS = [
    {"recipient_name": "JOSH FOR JERSEY", "total": 70730.0},
    {"recipient_name": "HALEY STEVENS FOR CONGRESS", "total": 5000.0},
]

NONPROFIT = {"organization": {"name": "AIPAC"}, "filings_with_data": [
    {"tax_prd_yr": 2023, "totrevenue": 79401004, "totfuncexpns": 83081062, "totassetsend": 170596173}]}


def fake_fec(path, **params):
    if path.endswith("/totals/"):
        row = TOTALS_UDP if "C00799031" in path else TOTALS_PAC
        return {"results": [row], "pagination": {"pages": 1}}
    if path == "/schedules/schedule_b/by_recipient/":
        return {"results": GIFTS, "pagination": {"pages": 1}}
    if path == "/schedules/schedule_b/":
        return {"results": SCHEDULE_B, "pagination": {"pages": 1}}
    if path == "/schedules/schedule_e/":
        cid = params.get("committee_id")
        rows = SCHEDULE_E_UDP if cid == refresh.UDP else SCHEDULE_E_CONDUIT
        return {"results": rows, "pagination": {"pages": 1}}
    if path.startswith("/committee/C"):
        return {"results": [{"committee_type_full": "Super PAC",
                             "connected_org_name": "DEMOCRATS 2024"}], "pagination": {"pages": 1}}
    raise AssertionError(f"unexpected endpoint {path}")


class ApiPathTest(unittest.TestCase):
    def setUp(self):
        refresh.API_KEY = "TEST"
        patches = [
            mock.patch.object(refresh, "fec", side_effect=fake_fec),
            mock.patch.object(refresh, "http_json", return_value=NONPROFIT),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_collect(self):
        seed, derived = refresh.collect_api(2026)

        self.assertEqual(seed["committees"]["UDP"]["receipts"], 112820861.12)
        self.assertEqual(seed["coverage_end"], "2026-10-14")

        # only committee recipients become middlemen
        self.assertEqual(len(derived["conduits"]), 2)
        ecw = next(c for c in derived["conduits"] if c["id"] == "C00936724")
        self.assertEqual(ecw["amount"], 4011200.0)
        self.assertEqual(ecw["spent"], 9795804.0)
        self.assertEqual(ecw["first_spend"], "2026-02-04")
        self.assertEqual(ecw["last_spend"], "2026-03-12")

        self.assertEqual(len(derived["independent_expenditures"]), 2)
        self.assertEqual(derived["ie_total"], 30658712.0)
        self.assertEqual(derived["aipac_pac_gift_total"], 75730.0)

    def test_bare_schedule_b_fails_loudly(self):
        def empty(path, **params):
            if path == "/schedules/schedule_b/":
                return {"results": [], "pagination": {"pages": 1}}
            return fake_fec(path, **params)
        with mock.patch.object(refresh, "fec", side_effect=empty):
            with self.assertRaises(RuntimeError):
                refresh.collect_api(2026)


if __name__ == "__main__":
    unittest.main()
