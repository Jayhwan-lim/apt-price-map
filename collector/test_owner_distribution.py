import unittest
from owner_distribution import estimate, round_counts, recent_median


def trade(date, price, dong="", direct=0, cancelled=0, floor=3):
    return [date, 27.68, floor, price, direct, cancelled, dong]


class OwnerDistributionTest(unittest.TestCase):
    pools = [["101", 3, 27.68, 1], ["102", 3, 27.68, 1]]
    types = {"27": [27.68, 27.68, 27.68, 2]}

    def calc(self, rows, **kw):
        return estimate(rows, self.pools, "27", self.types, "2026-10-11", **kw)

    def test_known_repeated_sale_retains_latest_price(self):
        d = self.calc([trade("20250101", 100000, "101동"),
                       trade("20150101", 20000, "101"), trade("20100101", 40000, "102")])
        self.assertEqual(d["assigned"], 2)
        self.assertEqual({lo: n for lo, hi, n in d["bins"] if n}, {40000: 1, 100000: 1})

    def test_missing_dong_accounts_for_repeat_probability(self):
        d = self.calc([trade("20250101", 100000), trade("20150101", 20000)])
        self.assertEqual(d["expectedAssigned"], 1.5)
        self.assertEqual(sum(x[2] for x in d["bins"]) + d["unknown"], 2)

    def test_recent_missing_and_older_known_share_capacity(self):
        d = self.calc([trade("20250101", 100000), trade("20150101", 20000, "101")])
        self.assertEqual(d["expectedAssigned"], 1.5)
        reverse = self.calc([trade("20250101", 100000, "101"), trade("20150101", 20000)])
        self.assertEqual(reverse["expectedAssigned"], 1.5)

    def test_cancel_direct_and_future_filters(self):
        rows = [trade("20250101", 100000, "101"), trade("20240101", 40000, "102", direct=1),
                trade("20230101", 20000, "102", cancelled=1), trade("20270101", 60000, "102")]
        self.assertEqual(self.calc(rows)["assigned"], 1)
        self.assertEqual(self.calc(rows, include_direct=True)["assigned"], 2)

    def test_missing_capacity_blocks_instead_of_silently_dropping(self):
        with self.assertRaises(ValueError):
            self.calc([trade("20250101", 100000, "999")])
        with self.assertRaises(ValueError):
            self.calc([trade("20250101", 100000, floor=20)])

    def test_no_trades_and_tied_dates_are_deterministic(self):
        d = self.calc([])
        self.assertEqual((d["assigned"], d["unknown"]), (0, 2))
        rows = [trade("20250101", 20000), trade("20250101", 100000, "101")]
        self.assertEqual(self.calc(rows), self.calc(rows[::-1]))

    def test_market_widens_and_uses_median(self):
        rows = [trade("20261001", 150000), trade("20260901", 100000), trade("20260902", 120000)]
        d = recent_median(rows, "2026-10-11")
        self.assertEqual((d["months"], d["price"], d["n"]), (3, 120000, 3))
        self.assertEqual(sum(round_counts([.2, .8, 1.0], 2)), 2)


if __name__ == "__main__":
    unittest.main()
