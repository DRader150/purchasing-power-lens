"""Unit tests for series math. No network."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from series_math import (
    annual_average_ratio,
    basket_cost,
    basket_kcal,
    common_rebase,
    divide_series,
    month_key,
    monthly_mean,
    splice_gold,
)


class SeriesMathTests(unittest.TestCase):
    def test_month_key(self):
        self.assertEqual(month_key("2026-08-01"), "2026-08")
        self.assertEqual(month_key("2026-08"), "2026-08")

    def test_monthly_mean(self):
        averaged = monthly_mean(
            [("2020-01-02", 10), ("2020-01-20", 30), ("2020-02-01", 5)]
        )
        self.assertEqual(averaged["2020-01"], 20)
        self.assertEqual(averaged["2020-02"], 5)

    def test_divide_skips_missing_and_zero(self):
        points = divide_series({"2020-01": 10, "2020-02": 10}, {"2020-01": 2, "2020-02": 0})
        self.assertEqual(points, [["2020-01", 5]])

    def test_basket_requires_full_recipe(self):
        recipe = [
            {"series_id": "rice", "qty": 2, "kcal_per_unit": 100, "name": "rice",
             "qty_unit": "lb", "price_unit": "$/lb"},
            {"series_id": "milk", "qty": 0.5, "kcal_per_unit": 200, "name": "milk",
             "qty_unit": "gal", "price_unit": "$/gal"},
        ]
        prices = {
            "rice": {"2020-01": 1.0, "2020-02": 1.5},
            "milk": {"2020-02": 4.0},
        }
        points = basket_cost(prices, recipe)
        self.assertEqual(points, [["2020-02", 1.5 * 2 + 4.0 * 0.5]])
        self.assertAlmostEqual(basket_kcal(recipe), 2 * 100 + 0.5 * 200)

    def test_splice_gold_uses_fix_then_futures(self):
        wb = {f"{year}-{m:02d}": 1000 + m for year in (2020, 2021) for m in range(1, 13)}
        wb["2024-12"] = 2600
        comex = {f"{year}-{m:02d}": (1000 + m) * 1.01 for year in (2020, 2021) for m in range(1, 13)}
        comex["2024-12"] = 2620
        comex["2025-01"] = 2700
        points, meta = splice_gold(wb, comex)
        self.assertEqual(points[0]["source"], "world_bank")
        self.assertEqual(points[-1], {"t": "2025-01", "v": 2700, "source": "comex"})
        self.assertNotIn("2024-12", [p["t"] for p in points if p["source"] == "comex"])
        self.assertAlmostEqual(meta["medianComexOverWorldBank"], 1.01, places=2)

    def test_splice_rejects_bad_scale(self):
        wb = {f"{year}-{m:02d}": 1000 for year in (2020, 2021) for m in range(1, 13)}
        comex = {f"{year}-{m:02d}": 100 for year in (2020, 2021) for m in range(1, 13)}
        comex["2022-01"] = 100
        with self.assertRaises(ValueError):
            splice_gold(wb, comex)

    def test_common_rebase_and_annual_ratio(self):
        base, left, right = common_rebase(
            {"2020-01": 50, "2020-02": 100},
            {"2020-01": 25, "2020-02": 25, "2020-03": 25},
        )
        self.assertEqual(base, "2020-01")
        self.assertEqual(left[1][1], 200)
        self.assertEqual(right[1][1], 100)
        ratio = annual_average_ratio(
            {"2020-01": 100, "2020-06": 300, "2021-01": 10},
            {"2020": 2},
            min_months=2,
        )
        self.assertEqual(ratio, [["2020", 100]])


if __name__ == "__main__":
    unittest.main()
