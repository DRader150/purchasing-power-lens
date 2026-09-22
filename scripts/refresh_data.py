"""Download public series and write docs/data/series.json.

No API key. FRED CSV, a World Bank workbook, Yahoo chart JSON, and the
public BLS API. Re-run from the repo root:

    python3 scripts/refresh_data.py
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from series_math import (  # noqa: E402
    annual_average_ratio,
    as_map,
    basket_cost,
    basket_kcal,
    common_rebase,
    divide_series,
    latest_breakdown,
    month_key,
    monthly_mean,
    rebase_to,
    round_points,
    splice_gold,
)

OUT_PATH = ROOT / "docs" / "data" / "series.json"
USER_AGENT = "purchasing-power-lens/1.0 (public chart refresh; +https://github.com/DRader150/purchasing-power-lens)"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

# Fixed non-organic basket. Energy factors are USDA FoodData Central
# per-100 g figures applied to the BLS selling unit. They are not a lab
# assay of the CPI sample, and they are not an official USDA Food Plan.
# Whole chicken is priced per purchased pound, which includes bone, while
# the energy factor is edible meat and skin — that line overstates edible
# kilocalories. See the on-chart caveat.
FOOD_RECIPE = [
    {
        "series_id": "APU0000714233",
        "name": "Dried beans, any type",
        "qty": 2.0,
        "qty_unit": "lb",
        "price_unit": "$/lb",
        "kcal_per_100g": 341,
        "kcal_per_unit": 341 * 4.536,
        "energy_note": "USDA black beans, mature seeds, raw, 341 kcal/100 g, as a stand-in for the BLS any-type dried-bean price. Other dry beans are about 337–347 kcal/100 g.",
    },
    {
        "series_id": "APU0000701111",
        "name": "White all-purpose flour",
        "qty": 1.0,
        "qty_unit": "lb",
        "price_unit": "$/lb",
        "kcal_per_100g": 364,
        "kcal_per_unit": 364 * 4.536,
        "energy_note": "USDA wheat flour, all-purpose, enriched, 364 kcal/100 g.",
    },
    {
        "series_id": "APU0000702111",
        "name": "White pan bread",
        "qty": 1.0,
        "qty_unit": "lb",
        "price_unit": "$/lb",
        "kcal_per_100g": 266,
        "kcal_per_unit": 266 * 4.536,
        "energy_note": "USDA white bread, commercially prepared, 266 kcal/100 g.",
    },
    {
        "series_id": "APU0000701322",
        "name": "Dry spaghetti and macaroni",
        "qty": 0.5,
        "qty_unit": "lb",
        "price_unit": "$/lb",
        "kcal_per_100g": 371,
        "kcal_per_unit": 371 * 4.536,
        "energy_note": "USDA dry enriched pasta, 371 kcal/100 g.",
    },
    {
        "series_id": "APU0000708111",
        "name": "Eggs, grade A large",
        "qty": 1.0,
        "qty_unit": "dozen",
        "price_unit": "$/dozen",
        "kcal_per_100g": 143,
        "kcal_per_unit": 12 * 50 * 143 / 100,
        "energy_note": "USDA whole raw egg, 143 kcal/100 g, times a 50 g large egg, times 12.",
    },
    {
        "series_id": "APU0000703111",
        "name": "Ground chuck, 100% beef",
        "qty": 1.0,
        "qty_unit": "lb",
        "price_unit": "$/lb",
        "kcal_per_100g": 254,
        "kcal_per_unit": 254 * 4.536,
        "energy_note": "USDA raw ground beef, 80% lean / 20% fat, 254 kcal/100 g, used as a proxy for BLS ground chuck.",
    },
    {
        "series_id": "APU0000706111",
        "name": "Whole fresh chicken",
        "qty": 2.0,
        "qty_unit": "lb",
        "price_unit": "$/lb",
        "kcal_per_100g": 215,
        "kcal_per_unit": 215 * 4.536,
        "energy_note": "USDA broiler meat and skin, raw, 215 kcal/100 g (about NDB 171447). Applied to purchase weight; bone is not removed, so edible kcal are lower.",
    },
    {
        "series_id": "APU0000704111",
        "name": "Sliced bacon",
        "qty": 0.5,
        "qty_unit": "lb",
        "price_unit": "$/lb",
        "kcal_per_100g": 393,
        "kcal_per_unit": 393 * 4.536,
        "energy_note": "USDA pork, cured, bacon, unprepared, 393 kcal/100 g (FDC 168277).",
    },
    {
        "series_id": "APU0000711211",
        "name": "Bananas",
        "qty": 2.0,
        "qty_unit": "lb",
        "price_unit": "$/lb",
        "kcal_per_100g": 89,
        "kcal_per_unit": 89 * 4.536,
        "energy_note": "USDA bananas, raw, 89 kcal/100 g.",
    },
    {
        "series_id": "APU0000712311",
        "name": "Field-grown tomatoes",
        "qty": 1.5,
        "qty_unit": "lb",
        "price_unit": "$/lb",
        "kcal_per_100g": 18,
        "kcal_per_unit": 18 * 4.536,
        "energy_note": "USDA red tomatoes, raw, 18 kcal/100 g.",
    },
    {
        "series_id": "APU0000709112",
        "name": "Whole milk",
        "qty": 0.5,
        "qty_unit": "gallon",
        "price_unit": "$/gal",
        "kcal_per_100g": 61,
        "kcal_per_unit": 16 * (61 * 244 / 100),
        "energy_note": "USDA whole milk, 3.25% fat, 61 kcal/100 g. One cup taken as 244 g, 16 cups in a gallon.",
    },
]


def fetch_bytes(url: str, *, data: bytes | None = None, headers: dict | None = None) -> bytes:
    last_error: Exception | None = None
    for attempt in range(4):
        req_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        if headers:
            req_headers.update(headers)
        request = Request(url, data=data, headers=req_headers)
        try:
            with urlopen(request, timeout=60) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last_error}")


def fred_observations(series_id: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    raw = fetch_bytes(url)
    text = raw.decode("utf-8", "replace")
    if "observation_date" not in text.splitlines()[0]:
        raise RuntimeError(f"FRED {series_id} did not return CSV: {text[:180]!r}")
    rows: list[tuple[str, float]] = []
    for row in csv.DictReader(io.StringIO(text)):
        value = (row.get(series_id) or "").strip()
        if not value or value == ".":
            continue
        rows.append((row["observation_date"], float(value)))
    if len(rows) < 12:
        raise RuntimeError(f"FRED {series_id} returned only {len(rows)} observations")
    return rows


def yahoo_monthly_closes(symbol: str) -> dict[str, float]:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{symbol}?period1=0&period2=2000000000&interval=1mo"
    )
    payload = json.loads(fetch_bytes(url))
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    closes = result["indicators"]["quote"][0]["close"]
    points: dict[str, float] = {}
    for stamp, close in zip(timestamps, closes):
        if close is None:
            continue
        month = datetime.fromtimestamp(stamp, timezone.utc).strftime("%Y-%m")
        points[month] = float(close)
    if len(points) < 24:
        raise RuntimeError(f"Yahoo {symbol} returned only {len(points)} monthly closes")
    return points


def _excel_col(cell_ref: str) -> str:
    match = re.match(r"([A-Z]+)", cell_ref)
    if not match:
        raise ValueError(cell_ref)
    return match.group(1)


def world_bank_gold() -> dict[str, float]:
    """London afternoon gold fix, monthly average, USD per troy ounce.

    The stable World Bank pink-sheet workbook lags the present. The refresh
    keeps it through its last month and splices a labeled COMEX tail after that.
    """
    url = (
        "https://thedocs.worldbank.org/en/doc/"
        "5d903e848db1d1b83e0ec8f744e55570-0350012021/related/"
        "CMO-Historical-Data-Monthly.xlsx"
    )
    blob = fetch_bytes(url)
    with zipfile.ZipFile(io.BytesIO(blob)) as workbook:
        shared_root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
        strings: list[str] = []
        for item in shared_root.findall("m:si", NS):
            strings.append("".join(node.text or "" for node in item.findall(".//m:t", NS)))
        sheet = ET.fromstring(workbook.read("xl/worksheets/sheet2.xml"))

    def cell_value(cell: ET.Element) -> str | None:
        node = cell.find("m:v", NS)
        if node is None or node.text is None:
            return None
        if cell.attrib.get("t") == "s":
            return strings[int(node.text)]
        return node.text

    header: dict[str, str] = {}
    units: dict[str, str] = {}
    gold_col = None
    points: dict[str, float] = {}
    for cell in sheet.findall(".//m:c", NS):
        ref = cell.attrib.get("r")
        if not ref:
            continue
        column = _excel_col(ref)
        row_number = int(re.search(r"(\d+)$", ref).group(1))
        value = cell_value(cell)
        if value is None:
            continue
        if row_number == 5:
            header[column] = value
            if value.strip() == "Gold":
                gold_col = column
        elif row_number == 6:
            units[column] = value
        elif gold_col and column == gold_col and row_number >= 7:
            date_cell = None  # filled below
            points[ref] = value  # temporary, replaced in a second pass

    if gold_col is None:
        raise RuntimeError("World Bank workbook has no Gold column")
    if "troy" not in units.get(gold_col, "").lower():
        raise RuntimeError(f"unexpected gold unit {units.get(gold_col)!r}")

    dates: dict[int, str] = {}
    gold_by_row: dict[int, float] = {}
    for cell in sheet.findall(".//m:c", NS):
        ref = cell.attrib.get("r")
        if not ref:
            continue
        column = _excel_col(ref)
        row_number = int(re.search(r"(\d+)$", ref).group(1))
        if row_number < 7:
            continue
        value = cell_value(cell)
        if value is None:
            continue
        if column == "A":
            match = re.fullmatch(r"(\d{4})M(\d{2})", value.strip())
            if match:
                dates[row_number] = f"{match.group(1)}-{match.group(2)}"
        elif column == gold_col:
            try:
                gold_by_row[row_number] = float(value)
            except ValueError:
                continue

    series = {
        dates[row]: gold_by_row[row]
        for row in sorted(set(dates) & set(gold_by_row))
    }
    if len(series) < 120:
        raise RuntimeError(f"World Bank gold is too short ({len(series)})")
    return series


def bls_cpi_televisions() -> dict[str, float]:
    """CPI-U televisions, U.S. city average, not seasonally adjusted.

    Unregistered BLS queries allow about 10 years each. Chunks are merged.
    BLS rebased this item to December 2024 = 100; the API returns one continuous
    history on the current base.
    """
    series_id = "CUUR0000SERA01"
    merged: dict[str, float] = {}
    for start, end in (("1986", "1995"), ("1996", "2005"), ("2006", "2015"), ("2016", "2025"), ("2017", "2026")):
        body = json.dumps(
            {"seriesid": [series_id], "startyear": start, "endyear": end}
        ).encode()
        payload = json.loads(
            fetch_bytes(
                "https://api.bls.gov/publicAPI/v1/timeseries/data/",
                data=body,
                headers={"Content-Type": "application/json"},
            )
        )
        if payload.get("status") != "REQUEST_SUCCEEDED":
            raise RuntimeError(f"BLS {series_id} {start}-{end}: {payload.get('message')}")
        observations = payload["Results"]["series"][0]["data"]
        for obs in observations:
            period = obs.get("period", "")
            if not re.fullmatch(r"M(0[1-9]|1[0-2])", period):
                continue
            value = obs.get("value", "")
            if value in ("", "-"):
                continue
            merged[f"{obs['year']}-{period[1:]}"] = float(value)
        time.sleep(0.4)
    if len(merged) < 120:
        raise RuntimeError(f"CPI televisions is too short ({len(merged)})")
    # A rebase left in the chunks would show up as a huge one-month jump.
    ordered = [merged[month] for month in sorted(merged)]
    worst = max(ordered[i] / ordered[i - 1] for i in range(1, len(ordered)))
    worst_drop = min(ordered[i] / ordered[i - 1] for i in range(1, len(ordered)))
    if worst > 1.5 or worst_drop < 0.6:
        raise RuntimeError(
            f"CPI televisions has a broken join (month ratios {worst_drop:.3f} to {worst:.3f})"
        )
    return merged


def points_from_map(series: dict[str, float]) -> list[list[float | str]]:
    return round_points([[month, series[month]] for month in sorted(series)])


def require_overlap(name: str, points: list, minimum: int) -> None:
    if len(points) < minimum:
        raise RuntimeError(f"{name} has only {len(points)} points, need {minimum}")


def build() -> dict:
    print("Downloading FRED series...")
    fred_ids = [
        "DCOILWTICO",
        "GASREGW",
        "GASDESW",
        "APU000072610",
        "CUSR0000SEHG",
        "CUSR0000SETA01",
        "CUSR0000SEHF01",
        "CPIAUCSL",
        "MSPNHSUS",
        "AHETPI",
        "MEHOINUSA646N",
        "CBBTCUSD",
        "SP500",
        *[item["series_id"] for item in FOOD_RECIPE],
    ]
    fred: dict[str, list[tuple[str, float]]] = {}
    for series_id in fred_ids:
        print(f"  {series_id}")
        fred[series_id] = fred_observations(series_id)
        time.sleep(0.15)

    print("Downloading gold, S&P, and CPI televisions...")
    wb_gold = world_bank_gold()
    comex = yahoo_monthly_closes("GC%3DF")
    spx = yahoo_monthly_closes("%5EGSPC")
    televisions = bls_cpi_televisions()

    gold_points, gold_meta = splice_gold(wb_gold, comex)
    gold_map = {point["t"]: point["v"] for point in gold_points}

    oil = monthly_mean(fred["DCOILWTICO"])
    gasoline = monthly_mean(fred["GASREGW"])
    diesel = monthly_mean(fred["GASDESW"])
    electricity = monthly_mean(fred["APU000072610"])
    water = monthly_mean(fred["CUSR0000SEHG"])
    vehicles = monthly_mean(fred["CUSR0000SETA01"])
    elec_cpi = monthly_mean(fred["CUSR0000SEHF01"])
    cpi = monthly_mean(fred["CPIAUCSL"])
    house = monthly_mean(fred["MSPNHSUS"])
    wages = monthly_mean(fred["AHETPI"])
    btc = monthly_mean(fred["CBBTCUSD"])
    fred_spx_daily = fred["SP500"]

    income = {}
    for date_str, value in fred["MEHOINUSA646N"]:
        income[date_str[:4]] = value

    food_prices = {
        item["series_id"]: monthly_mean(fred[item["series_id"]]) for item in FOOD_RECIPE
    }
    food_points = basket_cost(food_prices, FOOD_RECIPE)
    require_overlap("food basket", food_points, 120)
    food_map = as_map([(row[0], row[1]) for row in food_points])
    kcal_week = basket_kcal(FOOD_RECIPE)
    latest_food_month = food_points[-1][0]
    breakdown = latest_breakdown(food_prices, FOOD_RECIPE, str(latest_food_month))

    fred_spx_month = monthly_mean(fred_spx_daily)
    spx_check_months = sorted(set(fred_spx_month) & set(spx))
    if not spx_check_months:
        raise RuntimeError("Yahoo S&P and FRED SP500 do not overlap")
    check_month = spx_check_months[-1]
    # Prefer a completed overlap month if the latest Yahoo month is still partial.
    if len(spx_check_months) > 1:
        check_month = spx_check_months[-2]
    fred_level = fred_spx_month[check_month]
    yahoo_level = spx[check_month]
    spx_ratio = yahoo_level / fred_level
    if not (0.97 <= spx_ratio <= 1.03):
        raise RuntimeError(
            f"Yahoo ^GSPC {yahoo_level} vs FRED SP500 monthly mean {fred_level} "
            f"in {check_month} (ratio {spx_ratio:.4f})"
        )

    house_gold = divide_series(house, gold_map)
    house_btc = divide_series(house, btc)
    food_gold = divide_series(food_map, gold_map)
    gas_oil = divide_series(gasoline, oil)
    gold_spx = divide_series(gold_map, spx)
    kwh_per_hour = divide_series(wages, electricity)
    house_income = annual_average_ratio(house, income)
    base_month, gold_indexed, spx_indexed = common_rebase(gold_map, spx)
    elec_vs_cpi_base = "1983-01"
    elec_rebased = {
        row[0]: row[1] for row in rebase_to(elec_cpi, elec_vs_cpi_base)
    }
    cpi_rebased = {row[0]: row[1] for row in rebase_to(cpi, elec_vs_cpi_base)}
    shared_cpi_months = sorted(set(elec_rebased) & set(cpi_rebased))
    elec_line = [[month, elec_rebased[month]] for month in shared_cpi_months]
    cpi_line = [[month, cpi_rebased[month]] for month in shared_cpi_months]

    require_overlap("house in gold", house_gold, 120)
    require_overlap("house in btc", house_btc, 24)
    require_overlap("food / gold", food_gold, 60)
    require_overlap("gas / oil", gas_oil, 60)
    require_overlap("gold / S&P", gold_spx, 60)
    require_overlap("kWh per wage hour", kwh_per_hour, 60)
    require_overlap("house / income", house_income, 20)

    life = [
        {
            "id": "oil",
            "title": "WTI crude oil",
            "kind": "dollars",
            "per": "barrel",
            "usdUnit": "dollars per barrel",
            "caveat": "Cushing, Oklahoma spot. Monthly average of daily prices. The newest month is partial until EIA finishes it.",
            "source": "EIA via FRED DCOILWTICO",
            "sourceUrl": "https://fred.stlouisfed.org/series/DCOILWTICO",
            "points": points_from_map(oil),
        },
        {
            "id": "gasoline",
            "title": "Regular gasoline",
            "kind": "dollars",
            "per": "gallon",
            "usdUnit": "dollars per gallon",
            "caveat": "U.S. regular, all formulations, retail. Weekly EIA prices averaged by month.",
            "source": "EIA via FRED GASREGW",
            "sourceUrl": "https://fred.stlouisfed.org/series/GASREGW",
            "points": points_from_map(gasoline),
        },
        {
            "id": "diesel",
            "title": "Diesel",
            "kind": "dollars",
            "per": "gallon",
            "usdUnit": "dollars per gallon",
            "caveat": "U.S. diesel sales price. Weekly EIA prices averaged by month.",
            "source": "EIA via FRED GASDESW",
            "sourceUrl": "https://fred.stlouisfed.org/series/GASDESW",
            "points": points_from_map(diesel),
        },
        {
            "id": "electricity",
            "title": "Residential electricity",
            "kind": "dollars",
            "per": "kWh",
            "usdUnit": "dollars per kWh",
            "caveat": "U.S. city-average price per kilowatt-hour. Not a particular utility bill.",
            "source": "BLS average price via FRED APU000072610",
            "sourceUrl": "https://fred.stlouisfed.org/series/APU000072610",
            "points": points_from_map(electricity),
        },
        {
            "id": "water",
            "title": "Water, sewer, and trash*",
            "kind": "index",
            "per": "index point",
            "usdUnit": "CPI index points",
            "caveat": "Not a gallon of water and not a water bill. CPI-U for water, sewer, and trash collection together, seasonally adjusted. U.S. city average. The series begins in 1997.",
            "source": "BLS via FRED CUSR0000SEHG",
            "sourceUrl": "https://fred.stlouisfed.org/series/CUSR0000SEHG",
            "points": points_from_map(water),
        },
        {
            "id": "food",
            "title": "Food week*",
            "kind": "dollars",
            "per": "food week",
            "usdUnit": "dollars per food week",
            "caveat": (
                f"A fixed non-organic basket of about {kcal_week / 7:,.0f} kcal/day "
                f"({kcal_week:,.0f} kcal in the week), built from BLS city-average shelf prices. "
                "Not an official USDA Food Plan and not a household grocery bill. "
                "No organic premium. Whole-chicken calories are overstated because the price includes bone. "
                "Dried beans stand in for rice: the white-rice city average was unpublished for two years (2000–2002), and navel-orange prices are seasonal, so those series were left out rather than filled in. "
                "A month is blank when any ingredient was not published. Nothing is carried forward. "
                "The basket starts July 1995, when the whole-milk gallon series starts."
            ),
            "source": "BLS average prices via FRED, recipe in the sources section",
            "sourceUrl": "https://fred.stlouisfed.org/release?rid=454",
            "points": round_points(food_points),
        },
        {
            "id": "vehicles",
            "title": "New vehicles*",
            "kind": "index",
            "per": "index point",
            "usdUnit": "CPI index points",
            "caveat": "Not a sticker price and not the average transaction price. CPI-U new vehicles, seasonally adjusted, 1982–84 = 100. A long public dollar series for the average new car was not available, so the car/food-week ratio is omitted.",
            "source": "BLS via FRED CUSR0000SETA01",
            "sourceUrl": "https://fred.stlouisfed.org/series/CUSR0000SETA01",
            "points": points_from_map(vehicles),
        },
        {
            "id": "televisions",
            "title": "Televisions*",
            "kind": "index",
            "per": "index point",
            "usdUnit": "CPI index points",
            "caveat": "Not the shelf price of a flat screen. CPI-U televisions, not seasonally adjusted, December 2024 = 100 after the 2026 rebase. Quality-adjusted, and the history includes tube sets before flat panels. Gold and bitcoin views are index points per ounce or coin, not a TV’s price tag.",
            "source": "BLS CUUR0000SERA01",
            "sourceUrl": "https://data.bls.gov/timeseries/CUUR0000SERA01",
            "points": points_from_map(televisions),
        },
    ]

    charts = [
        {
            "id": "house-gold",
            "section": "monetary",
            "title": "U.S. new-house price in gold",
            "subtitle": "Median sales price of new houses sold, divided by that month’s gold price. Dollars cancel. New houses, not the existing-home median.",
            "yLabel": "troy ounces per house",
            "log": False,
            "source": "Census/HUD via FRED MSPNHSUS, divided by the gold series below.",
            "sourceUrl": "https://fred.stlouisfed.org/series/MSPNHSUS",
            "series": [{"name": "Ounces of gold", "points": round_points(house_gold)}],
        },
        {
            "id": "house-btc",
            "section": "monetary",
            "title": "U.S. new-house price in bitcoin",
            "subtitle": "Same median new-house price, divided by the monthly average Coinbase bitcoin price. Starts December 2014, the first month of FRED CBBTCUSD. Log scale so the early years do not hide the recent level.",
            "yLabel": "bitcoin per house",
            "log": True,
            "source": "FRED MSPNHSUS ÷ FRED CBBTCUSD.",
            "sourceUrl": "https://fred.stlouisfed.org/series/CBBTCUSD",
            "series": [{"name": "Bitcoin per house", "points": round_points(house_btc)}],
        },
        {
            "id": "gold-vs-spx",
            "section": "monetary",
            "title": "Gold vs S&P 500",
            "subtitle": f"Both lines start at 100 in {base_month}, their first shared month. This is a price index, not a total-return index: dividends are not in the S&P line. Gold is the spliced series described in Sources.",
            "yLabel": f"Index ({base_month} = 100)",
            "log": False,
            "source": "World Bank / Yahoo GC=F gold, and Yahoo Finance ^GSPC monthly close.",
            "sourceUrl": "https://finance.yahoo.com/quote/%5EGSPC/",
            "series": [
                {"name": "Gold", "points": round_points(gold_indexed)},
                {"name": "S&P 500", "points": round_points(spx_indexed)},
            ],
        },
        {
            "id": "btc-usd",
            "section": "monetary",
            "title": "Bitcoin purchasing power vs the dollar",
            "subtitle": "Dollars one bitcoin exchanged for on Coinbase, monthly average, log scale. Nominal: this is not adjusted by CPI. It is the purchasing power of a bitcoin measured in dollars.",
            "yLabel": "dollars per bitcoin",
            "log": True,
            "source": "Coinbase via FRED CBBTCUSD.",
            "sourceUrl": "https://fred.stlouisfed.org/series/CBBTCUSD",
            "series": [{"name": "Bitcoin in dollars", "points": points_from_map(btc)}],
        },
        {
            "id": "house-income",
            "section": "monetary",
            "title": "New house vs household income",
            "subtitle": "Average of that year’s monthly median new-house prices, divided by nominal median household income. A reading of 4 means the median new house cost four years of the median household’s pretax income. Income is annual and lags; a year is skipped until income is published and at least six house months exist.",
            "yLabel": "years of median household income",
            "log": False,
            "source": "FRED MSPNHSUS and FRED MEHOINUSA646N (nominal, not the real 672N series).",
            "sourceUrl": "https://fred.stlouisfed.org/series/MEHOINUSA646N",
            "series": [{"name": "Years of income", "points": round_points(house_income, 4)}],
        },
        {
            "id": "food-gold",
            "section": "ratios",
            "title": "Food week / gold",
            "subtitle": "Ounces of gold that buy one food week. Same basket as the life-cost strip.",
            "yLabel": "troy ounces per food week",
            "log": False,
            "source": "Food-week basket ÷ gold price.",
            "sourceUrl": "https://fred.stlouisfed.org/release?rid=454",
            "series": [{"name": "Ounces per food week", "points": round_points(food_gold)}],
        },
        {
            "id": "gas-oil",
            "section": "ratios",
            "title": "Gas / oil",
            "subtitle": "Retail regular gasoline ($/gal) divided by WTI ($/bbl). A barrel is 42 gallons, so 1/42 ≈ 0.0238 would mean the gallon at the pump cost the same as a gallon of crude, with no refining, tax, or station margin. The dashed line is that benchmark, not a price forecast.",
            "yLabel": "($ per gallon) / ($ per barrel)",
            "log": False,
            "source": "FRED GASREGW ÷ monthly average of FRED DCOILWTICO.",
            "sourceUrl": "https://fred.stlouisfed.org/series/GASREGW",
            "series": [
                {"name": "Gas / oil", "points": round_points(gas_oil)},
                {
                    "name": "1/42 crude-only benchmark",
                    "points": [[row[0], 1 / 42] for row in gas_oil],
                    "dash": True,
                },
            ],
        },
        {
            "id": "ratio-house-gold",
            "section": "ratios",
            "title": "House / gold",
            "subtitle": "Same series as the monetary chart above: troy ounces per median new house.",
            "yLabel": "troy ounces per house",
            "log": False,
            "source": "FRED MSPNHSUS ÷ gold.",
            "sourceUrl": "https://fred.stlouisfed.org/series/MSPNHSUS",
            "series": [{"name": "Ounces of gold", "points": round_points(house_gold)}],
        },
        {
            "id": "ratio-house-btc",
            "section": "ratios",
            "title": "House / bitcoin",
            "subtitle": "Same series as the monetary chart. Log scale. Coinbase history only, from December 2014.",
            "yLabel": "bitcoin per house",
            "log": True,
            "source": "FRED MSPNHSUS ÷ FRED CBBTCUSD.",
            "sourceUrl": "https://fred.stlouisfed.org/series/CBBTCUSD",
            "series": [{"name": "Bitcoin per house", "points": round_points(house_btc)}],
        },
        {
            "id": "gold-spx",
            "section": "ratios",
            "title": "Gold / S&P",
            "subtitle": "Dollars per troy ounce divided by the S&P 500 price index. This is the reciprocal shape of “the index priced in gold,” kept here as the named ratio. Dividends are not included.",
            "yLabel": "(USD per oz) / index point",
            "log": False,
            "source": "Gold series ÷ Yahoo ^GSPC monthly close.",
            "sourceUrl": "https://finance.yahoo.com/quote/%5EGSPC/",
            "series": [{"name": "Gold / S&P", "points": round_points(gold_spx)}],
        },
        {
            "id": "elec-wage",
            "section": "ratios",
            "title": "Electricity vs wages",
            "subtitle": "Kilowatt-hours one hour of pay buys. Pay is average hourly earnings of private production and nonsupervisory workers, gross, not household income and not after tax.",
            "yLabel": "kWh per hour of pay",
            "log": False,
            "source": "FRED AHETPI ÷ FRED APU000072610.",
            "sourceUrl": "https://fred.stlouisfed.org/series/AHETPI",
            "series": [{"name": "kWh per hour", "points": round_points(kwh_per_hour)}],
        },
        {
            "id": "elec-cpi",
            "section": "ratios",
            "title": "Electricity vs CPI",
            "subtitle": "CPI-U electricity and CPI-U all items, each rebased to 100 in January 1983 (inside the 1982–84 CPI base). A rising gap means the electricity index outpaced the all-items index after that date.",
            "yLabel": "Index (Jan 1983 = 100)",
            "log": False,
            "source": "FRED CUSR0000SEHF01 and FRED CPIAUCSL.",
            "sourceUrl": "https://fred.stlouisfed.org/series/CUSR0000SEHF01",
            "series": [
                {"name": "Electricity CPI", "points": round_points(elec_line)},
                {"name": "All-items CPI", "points": round_points(cpi_line)},
            ],
        },
    ]

    recipe_public = []
    for item, row in zip(FOOD_RECIPE, breakdown):
        recipe_public.append(
            {
                "name": item["name"],
                "seriesId": item["series_id"],
                "fredUrl": f"https://fred.stlouisfed.org/series/{item['series_id']}",
                "qty": item["qty"],
                "qtyUnit": item["qty_unit"],
                "kcalPerUnit": round(item["kcal_per_unit"], 2),
                "energyNote": item["energy_note"],
                "latestPrice": round(row["price"], 4),
                "latestLineCost": round(row["lineCost"], 4),
            }
        )

    document = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "siteName": "Purchasing Power Lens",
        "explainerUrl": "https://drader150.github.io/The-Debt-Based-Monetary-System-for-Everyday-People/",
        "explainerRepo": "https://github.com/DRader150/The-Debt-Based-Monetary-System-for-Everyday-People",
        "repoUrl": "https://github.com/DRader150/purchasing-power-lens",
        "gold": {
            "unit": "USD per troy ounce",
            "caveat": (
                "Through "
                f"{gold_meta['lastWorldBankMonth']}: World Bank monthly average of the London afternoon fixing "
                "(99.5% fine, nominal USD per troy ounce). After that month the World Bank file used here has not "
                "been updated, so the tail is the COMEX front-month gold futures monthly close (Yahoo GC=F), "
                "not the London fix. The two were checked on their overlap and were not rescaled."
            ),
            "splice": {
                "overlapMonths": gold_meta["overlapMonths"],
                "medianComexOverWorldBank": round(gold_meta["medianComexOverWorldBank"], 4),
                "lastWorldBankMonth": gold_meta["lastWorldBankMonth"],
                "firstComexOnlyMonth": gold_meta["firstComexOnlyMonth"],
                "boundaryRatio": round(gold_meta["boundaryRatio"], 4),
            },
            "sources": [
                {
                    "name": "World Bank Commodity Markets, monthly prices (pink sheet)",
                    "url": "https://www.worldbank.org/en/research/commodity-markets",
                },
                {
                    "name": "Yahoo Finance GC=F COMEX gold futures, monthly close",
                    "url": "https://finance.yahoo.com/quote/GC=F/",
                },
            ],
            "points": round_points([[point["t"], point["v"]] for point in gold_points], 4),
        },
        "btc": {
            "unit": "USD per bitcoin",
            "caveat": "Monthly average of the daily Coinbase bitcoin price on FRED. Earlier bitcoin prints are not used.",
            "source": "Coinbase via FRED CBBTCUSD",
            "sourceUrl": "https://fred.stlouisfed.org/series/CBBTCUSD",
            "points": points_from_map(btc),
        },
        "foodBasket": {
            "kcalPerWeek": round(kcal_week, 1),
            "kcalPerDay": round(kcal_week / 7, 1),
            "latestMonth": latest_food_month,
            "latestCost": round(float(food_points[-1][1]), 2),
            "recipe": recipe_public,
        },
        "checks": {
            "sp500": {
                "month": check_month,
                "yahooMonthlyClose": round(yahoo_level, 2),
                "fredMonthlyMean": round(fred_level, 2),
                "ratio": round(spx_ratio, 4),
            }
        },
        "omitted": [
            {
                "name": "Car / food week",
                "reason": "No long public dollar series for the average U.S. new-car transaction price was found. CPI new vehicles is an index and is on the life-cost strip. Dividing that index by the food-week dollar cost would mix units, so the ratio is omitted.",
            },
            {
                "name": "Existing-home median in gold or bitcoin",
                "reason": "FRED HOSMEDUSM052N did not return a long history from the public CSV endpoint during this refresh (a short recent sample only). House charts use the Census median sales price of new houses (MSPNHSUS).",
            },
            {
                "name": "Official USDA food-plan dollar cost",
                "reason": "USDA food plans are published as spreadsheets and PDFs, not as a stable keyless series. The food week is an explicit BLS-price reconstruction.",
            },
        ],
        "life": life,
        "charts": charts,
    }
    return document


def main() -> None:
    document = build()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"  generated {document['generatedAt']}")
    print(f"  gold {document['gold']['points'][0][0]} → {document['gold']['points'][-1][0]} = {document['gold']['points'][-1][1]}")
    print(f"  btc  {document['btc']['points'][0][0]} → {document['btc']['points'][-1][0]} = {document['btc']['points'][-1][1]}")
    print(
        f"  food {document['foodBasket']['latestMonth']} "
        f"${document['foodBasket']['latestCost']} "
        f"({document['foodBasket']['kcalPerDay']} kcal/day)"
    )


if __name__ == "__main__":
    main()
