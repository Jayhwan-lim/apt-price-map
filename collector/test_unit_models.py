import unittest
import sys
import types
from unittest.mock import patch

from audit_unit_models import audit, distribution_gap
from simulate_unit_assignment import assign_once, simulate
from unit_inventory import count_units, pages


class InventoryTest(unittest.TestCase):
    def test_anonymous_assignment_keeps_latest_and_respects_reported_dong(self):
        slots = {3: [("101", 0), ("102", 0)]}
        trades = [["20250101", 35.12, 3, 50000, 0, 0, "101동"],
                  ["20150101", 35.12, 3, 20000, 0, 0, "101동"],
                  ["20130101", 35.12, 3, 30000, 0, 0, "102동"]]
        assigned = assign_once(trades, slots, 1, 1)
        self.assertEqual(sorted(r[3] for r in assigned), [30000, 50000])
        out = simulate(trades, [["101동", 3, 35.12, 1],
                                ["102동", 3, 35.12, 1]], "35",
                       {"35": [35.0, 35.5, 35.12, 2]}, repetitions=3)
        self.assertEqual(out["newest_per_floor_baseline"]["median_manwon"], 35000)
        with self.assertRaises(ValueError):
            simulate(trades + [["20260101", 35.12, 3, 90000, 0, 0, "999동"]],
                     [["101동", 3, 35.12, 1], ["102동", 3, 35.12, 1]],
                     "35", {"35": [35.0, 35.5, 35.12, 2]}, repetitions=3)

    def test_api_page_cap_does_not_truncate_inventory(self):
        class Response:
            def __init__(self, page):
                self.page = page
            def raise_for_status(self):
                pass
            def json(self):
                n = 2 if self.page < 3 else 1
                return {"response": {"header": {"resultCode": "00"},
                        "body": {"totalCount": 5,
                                 "items": {"item": [{"page": self.page}] * n}}}}
        class Session:
            def get(self, url, params, timeout):
                return Response(params["pageNo"])
        entry = {"sigunguCd": "11710", "bjdongCd": "10200", "bun": "0017", "ji": "0000"}
        with patch.dict(sys.modules, {"requests": types.SimpleNamespace(RequestException=Exception)}):
            self.assertEqual(len(list(pages(Session(), "dummy", entry, "getBrExposInfo"))), 5)

    def test_count_unique_households_and_reject_mismatch(self):
        rows = [{"bldNm": "Park", "mainPurpsCdNm": "", "dongNm": "101동",
                 "hoNm": str(i), "flrNo": "3"} for i in (301, 302)]
        areas = [{"bldNm": "Park", "exposPubuseGbCdNm": "전유",
                  "dongNm": "101", "hoNm": f"{i}호", "area": "35.12"} for i in (301, 302)]
        entry = {"complex_key": "park", "building_names": ["Park"],
                 "housing_dongs": ["101동"], "expected_units": 2}
        result = count_units(rows, areas, entry)
        self.assertEqual(result["pools"], [["101", 3, 35.12, 2]])
        with self.assertRaises(ValueError):
            count_units(rows, areas, {**entry, "expected_units": 3})
        with self.assertRaises(ValueError):
            count_units(rows + rows[:1], areas, entry)
        with self.assertRaises(ValueError):
            count_units(rows, areas[:1], entry)
        commercial_area = {"bldNm": "Park", "exposPubuseGbCdNm": "전유",
                           "dongNm": "상가", "hoNm": "101", "area": "40"}
        result = count_units(rows, areas + [commercial_area], entry)
        self.assertEqual(result["expected_units"], 2)

    def test_distribution_gap_uses_full_price_cdf_and_same_cohort(self):
        left = [[None, None, None, 100], [None, None, None, 200]]
        right = [[None, None, None, 100], [None, None, None, 300]]
        gap = distribution_gap(left, right)
        self.assertEqual(gap["median_gap_manwon"], -50)
        self.assertEqual(gap["cdf_max_gap"], 0.5)
        self.assertEqual(gap["selection_count_gap"], 0)
        self.assertIsNone(distribution_gap([], right)["cdf_max_gap"])

    def test_actual_capacity_can_retain_old_trade(self):
        # Two actual units, one observed dong-floor slot. Latest-N F must
        # retain the older transaction with capacity 2, not capacity 1.
        rows = [["20250101", 35.12, 3, 50000, 0, 0, "101동"],
                ["20150101", 35.12, 3, 20000, 0, 0, ""]]
        out = audit(rows, [["101동", 3, 35.12, 2]], "35",
                    {"35": [35.0, 35.5, 35.12, 2]})
        self.assertEqual(out["verified_units"], 2)
        self.assertEqual(out["F_all"]["pre_2023_selected"], 1)
        self.assertEqual(out["D_known"]["unfilled_slots"], 1)
        self.assertEqual(out["dong_unmatched"], 0)
        with self.assertRaises(ValueError):
            audit(rows, [["101동", 3, 60.0, 2]], "35",
                  {"35": [35.0, 35.5, 35.12, 2]})


if __name__ == "__main__":
    unittest.main()
