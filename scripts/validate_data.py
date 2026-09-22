"""Check docs/data/series.json without hitting the network."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs" / "data" / "series.json"

REQUIRED_LIFE = (
    "oil",
    "gasoline",
    "diesel",
    "electricity",
    "water",
    "food",
    "vehicles",
    "televisions",
)
REQUIRED_CHARTS = (
    "house-gold",
    "house-btc",
    "gold-vs-spx",
    "btc-usd",
    "food-gold",
    "gas-oil",
    "ratio-house-gold",
    "ratio-house-btc",
    "gold-spx",
    "elec-wage",
    "elec-cpi",
)


def fail(message: str) -> None:
    raise SystemExit(message)


def series_ok(points: list, name: str, minimum: int) -> None:
    if len(points) < minimum:
        fail(f"{name} has {len(points)} points, need {minimum}")
    last_month = ""
    for point in points:
        month = point[0]
        value = point[1]
        if not isinstance(month, str) or len(month) < 4:
            fail(f"{name} has a bad date {month!r}")
        if month < last_month:
            fail(f"{name} is not sorted at {month}")
        last_month = month
        if not isinstance(value, (int, float)) or value <= 0:
            fail(f"{name} has a non-positive value at {month}: {value}")


def main() -> None:
    if not PATH.exists():
        fail(f"missing {PATH}; run scripts/refresh_data.py")
    document = json.loads(PATH.read_text(encoding="utf-8"))
    life = {item["id"]: item for item in document["life"]}
    for series_id in REQUIRED_LIFE:
        if series_id not in life:
            fail(f"missing life series {series_id}")
        series_ok(life[series_id]["points"], series_id, 60)
        if not life[series_id].get("caveat") or not life[series_id].get("source"):
            fail(f"{series_id} is missing a caveat or source")

    charts = {item["id"]: item for item in document["charts"]}
    for chart_id in REQUIRED_CHARTS:
        if chart_id not in charts:
            fail(f"missing chart {chart_id}")
        chart = charts[chart_id]
        if not chart.get("series"):
            fail(f"{chart_id} has no series")
        for index, series in enumerate(chart["series"]):
            series_ok(series["points"], f"{chart_id}[{index}]", 2)

    gold = document["gold"]["points"]
    btc = document["btc"]["points"]
    series_ok(gold, "gold", 200)
    series_ok(btc, "btc", 24)
    if gold[-1][1] < 1000:
        fail(f"gold latest {gold[-1]} looks too low for USD/oz")
    if btc[0][0] < "2014-12":
        fail("bitcoin series starts before the Coinbase FRED history")
    if btc[-1][1] < 1000:
        fail(f"bitcoin latest {btc[-1]} looks too low")

    food = life["food"]["points"]
    if not (15 <= food[-1][1] <= 200):
        fail(f"food-week latest cost {food[-1]} is outside $15–$200")
    basket = document["foodBasket"]
    if not (1500 <= basket["kcalPerDay"] <= 2500):
        fail(f"food basket is {basket['kcalPerDay']} kcal/day, expected near 2000")

    gasoline = life["gasoline"]["points"][-1][1]
    oil = life["oil"]["points"][-1][1]
    power = life["electricity"]["points"][-1][1]
    if not (1 <= gasoline <= 10):
        fail(f"gasoline latest {gasoline} is implausible")
    if not (20 <= oil <= 250):
        fail(f"oil latest {oil} is implausible")
    if not (0.05 <= power <= 1):
        fail(f"electricity latest {power} is implausible")

    house_gold = charts["house-gold"]["series"][0]["points"][-1][1]
    if not (20 <= house_gold <= 2000):
        fail(f"house/gold latest {house_gold} oz is implausible")

    splice = document["gold"]["splice"]
    if not (0.90 <= splice["medianComexOverWorldBank"] <= 1.10):
        fail(f"gold splice ratio drifted: {splice}")

    omitted = " ".join(item["name"].lower() for item in document.get("omitted", []))
    if "car / food" not in omitted:
        fail("expected an explicit omission for the car/food ratio")

    if life["water"]["kind"] != "index" or life["vehicles"]["kind"] != "index":
        fail("water and new vehicles must stay labeled as indexes")
    if life["televisions"]["kind"] != "index":
        fail("televisions must stay labeled as an index")

    print(f"OK {PATH}")
    print(f"  generated {document['generatedAt']}")
    print(f"  life series {len(life)}, charts {len(charts)}")
    print(f"  gold {gold[-1]}, btc {btc[-1]}, food {food[-1]}")


if __name__ == "__main__":
    main()
