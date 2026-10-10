import unittest

from audit_unit_models import audit
from unit_inventory import count_units


class InventoryTest(unittest.TestCase):
    def test_count_unique_households_and_reject_mismatch(self):
        rows = [{"bldNm": "Park", "mainPurpsCdNm": "아파트", "dongNm": "101동",
                 "hoNm": str(i), "flrNo": "3", "area": "35.12"} for i in (301, 302)]
        entry = {"complex_key": "park", "building_names": ["Park"], "expected_units": 2}
        result = count_units(rows, entry)
        self.assertEqual(result["pools"], [["101동", 3, 35.12, 2]])
        with self.assertRaises(ValueError):
            count_units(rows, {**entry, "expected_units": 3})
        with self.assertRaises(ValueError):
            count_units(rows + rows[:1], entry)

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
