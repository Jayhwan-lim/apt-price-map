import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from building_facts import SupplyScan, covered, spread_order, title_record  # noqa: E402
from map_metrics import jibun_of, pick_hub, pick_kapt, same_name, supply_for  # noqa: E402


def unit_rows(dong, ho, exclusive, stairs, walls, parking):
    base = {"dongNm": dong, "hoNm": ho, "flrGbCdNm": "지상"}
    return [
        {**base, "exposPubuseGbCd": "1", "mainPurpsCdNm": "아파트", "etcPurps": "아파트", "area": exclusive},
        {**base, "exposPubuseGbCd": "2", "mainPurpsCdNm": "아파트", "etcPurps": "계단실,승강기", "area": stairs},
        {**base, "exposPubuseGbCd": "2", "mainPurpsCdNm": "아파트", "etcPurps": "벽체", "area": walls},
        {**base, "exposPubuseGbCd": "2", "mainPurpsCdNm": "부대시설", "etcPurps": "지하주차장", "area": parking},
    ]


class SpreadOrderTest(unittest.TestCase):
    def test_visits_every_page_once_and_ends_early(self):
        for n in (1, 2, 3, 7, 50):
            order = spread_order(n)
            self.assertEqual(sorted(order), list(range(1, n + 1)))
        self.assertEqual(spread_order(9)[:3], [1, 9, 5])


class SupplyScanTest(unittest.TestCase):
    def test_supply_is_exclusive_plus_residential_common(self):
        scan = SupplyScan(1)
        rows = []
        for ho in ("101", "102", "103"):
            rows += unit_rows("201동", ho, 84.99, 18.48, 5.93, 58.29)
        scan.add_page(1, rows)
        self.assertEqual(scan.table(), {"84.99": [3, 109.4]})

    def test_units_cut_by_unread_pages_are_ignored(self):
        scan = SupplyScan(3)
        rows = unit_rows("1동", "101", 59.9, 17.0, 5.0, 40.0) + unit_rows("1동", "102", 59.9, 17.0, 5.0, 40.0)
        scan.add_page(2, rows)  # pages 1 and 3 unread: both edge units may be partial
        self.assertEqual(scan.table(), {})
        scan.add_page(1, unit_rows("1동", "100", 59.9, 17.0, 5.0, 40.0))
        # page 1 read: unit 101 (first on page 2) is complete; 102 still cut
        self.assertEqual(scan.table(), {"59.90": [2, 81.9]})  # 100 and 101; 102 still cut

    def test_register_without_common_rows_is_dropped(self):
        scan = SupplyScan(1)
        scan.add_page(1, unit_rows("1동", "101", 84.0, 0, 0, 30.0))
        self.assertEqual(scan.table(), {})

    def test_covered(self):
        table = {"84.99": [3, 109.4], "59.99": [1, 82.2]}
        self.assertTrue(covered(table, [[84.9, 85.0]]))
        self.assertFalse(covered(table, [[84.9, 85.0], [59.99, 59.99]]))
        self.assertTrue(covered(table, [[59.99, 59.99]], min_units=1))


class MatchingTest(unittest.TestCase):
    def test_jibun_from_kapt_address(self):
        self.assertEqual(jibun_of("서울특별시 송파구 잠실동 22 잠실리센츠", "잠실동"), "22")
        self.assertEqual(jibun_of("경기도 화성시 청계동 123-4 동탄역시범", "청계동"), "123-4")
        self.assertIsNone(jibun_of("서울특별시 송파구 신천동 17", "잠실동"))

    def test_names(self):
        self.assertTrue(same_name("잠실리센츠", "리센츠"))
        self.assertTrue(same_name("성원대치2단지아파트", "성원대치2단지"))
        self.assertFalse(same_name("삼익대청", "성원대치2단지"))

    def test_pick_hub_needs_name_on_shared_lots(self):
        rec = {"r": [title_record({"bldNm": "삼익대청", "hhldCnt": "120", "platArea": "9000"}),
                     title_record({"bldNm": "성원대치2단지", "hhldCnt": "1758", "platArea": "40000"})]}
        hit, named = pick_hub(rec, "성원대치2단지아파트", True)
        self.assertEqual((hit["u"], named), (1758, True))
        self.assertEqual(pick_hub({"r": rec["r"][:1]}, "개포우성", True), (None, False))

    def test_pick_kapt_same_lot(self):
        cands = [{"addr": "서울특별시 송파구 잠실동 22 잠실리센츠", "nm": "잠실리센츠", "u": 5563},
                 {"addr": "서울특별시 송파구 잠실동 19 잠실엘스", "nm": "잠실엘스", "u": 5678}]
        entry = {"umd": "잠실동", "jibun": "22"}
        self.assertEqual(pick_kapt(cands, entry, "리센츠", False)["u"], 5563)
        self.assertIsNone(pick_kapt(cands, {"umd": "잠실동", "jibun": "1"}, "리센츠", False))

    def test_supply_for_types(self):
        table = {"84.99": [234, 109.4], "59.99": [22, 82.22], "27.68": [69, 42.4]}
        ty = {"84": [84.99, 84.99, 84.99, 10], "59": [59.99, 59.99, 59.99, 3], "114": [114.9, 114.9, 114.9, 1]}
        self.assertEqual(supply_for(table, ty), {"84": (84.99, 109.4), "59": (59.99, 82.22)})


if __name__ == "__main__":
    unittest.main()
