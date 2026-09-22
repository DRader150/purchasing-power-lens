"""Pure transforms for Purchasing Power Lens.

Price observations stay as published. These helpers only average, divide,
rebase, or splice series that the refresh script has already downloaded.
"""

from __future__ import annotations

from collections import defaultdict


def month_key(date_str: str) -> str:
    """Return YYYY-MM from a YYYY-MM-DD or YYYY-MM string."""
    text = date_str.strip()
    if len(text) < 7 or text[4] != "-":
        raise ValueError(f"not a month date: {date_str!r}")
    year = int(text[0:4])
    month = int(text[5:7])
    if month < 1 or month > 12:
        raise ValueError(f"bad month in {date_str!r}")
    if year < 1800 or year > 2200:
        raise ValueError(f"bad year in {date_str!r}")
    return f"{year:04d}-{month:02d}"


def monthly_mean(observations: list[tuple[str, float]]) -> dict[str, float]:
    """Average observations that fall in the same calendar month."""
    buckets: dict[str, list[float]] = defaultdict(list)
    for date_str, value in observations:
        if value is None:
            continue
        buckets[month_key(date_str)].append(float(value))
    return {month: sum(values) / len(values) for month, values in buckets.items()}


def as_map(points: list[tuple[str, float]]) -> dict[str, float]:
    return {month: float(value) for month, value in points}


def sorted_points(series: dict[str, float]) -> list[list[float | str]]:
    return [[month, series[month]] for month in sorted(series)]


def divide_series(
    numerator: dict[str, float],
    denominator: dict[str, float],
) -> list[list[float | str]]:
    """Divide aligned months. Skip months where the denominator is missing or 0."""
    points: list[list[float | str]] = []
    for month in sorted(set(numerator) & set(denominator)):
        den = denominator[month]
        if den == 0:
            continue
        points.append([month, numerator[month] / den])
    return points


def basket_kcal(recipe: list[dict]) -> float:
    """Weekly kilocalories implied by the fixed recipe and its energy factors."""
    total = 0.0
    for item in recipe:
        total += float(item["qty"]) * float(item["kcal_per_unit"])
    return total


def basket_cost(
    prices: dict[str, dict[str, float]],
    recipe: list[dict],
) -> list[list[float | str]]:
    """Dollar cost of the recipe in months where every ingredient has a price.

    Missing months are left missing. Prices are not carried forward.
    """
    if not recipe:
        raise ValueError("recipe is empty")
    months: set[str] | None = None
    for item in recipe:
        series_id = item["series_id"]
        if series_id not in prices or not prices[series_id]:
            raise ValueError(f"no prices for {series_id}")
        keys = set(prices[series_id])
        months = keys if months is None else months & keys
    assert months is not None
    points: list[list[float | str]] = []
    for month in sorted(months):
        cost = 0.0
        for item in recipe:
            cost += prices[item["series_id"]][month] * float(item["qty"])
        points.append([month, cost])
    return points


def latest_breakdown(
    prices: dict[str, dict[str, float]],
    recipe: list[dict],
    month: str,
) -> list[dict]:
    rows = []
    for item in recipe:
        price = prices[item["series_id"]][month]
        qty = float(item["qty"])
        rows.append(
            {
                "name": item["name"],
                "seriesId": item["series_id"],
                "qty": qty,
                "qtyUnit": item["qty_unit"],
                "price": price,
                "priceUnit": item["price_unit"],
                "lineCost": price * qty,
                "kcal": qty * float(item["kcal_per_unit"]),
            }
        )
    return rows


def splice_gold(
    world_bank: dict[str, float],
    comex: dict[str, float],
    *,
    min_overlap: int = 24,
    median_ratio_band: tuple[float, float] = (0.90, 1.10),
) -> tuple[list[dict], dict]:
    """Use the London fix through its last month, then COMEX monthly closes.

    The median COMEX/World Bank ratio over the overlap must sit near 1.
    This refuses a bad column parse instead of scaling one series onto the other.
    """
    overlap = sorted(set(world_bank) & set(comex))
    if len(overlap) < min_overlap:
        raise ValueError(
            f"gold overlap is {len(overlap)} months, need at least {min_overlap}"
        )
    ratios = sorted(comex[month] / world_bank[month] for month in overlap)
    median = ratios[len(ratios) // 2]
    low, high = median_ratio_band
    if not (low <= median <= high):
        raise ValueError(
            f"COMEX/World Bank median ratio {median:.4f} is outside {low}-{high}"
        )
    last_wb = max(world_bank)
    first_tail = min(month for month in comex if month > last_wb) if any(
        month > last_wb for month in comex
    ) else None
    if first_tail is None:
        raise ValueError("COMEX series does not extend past the World Bank file")
    boundary_ratio = comex[first_tail] / world_bank[last_wb]
    if not (0.70 <= boundary_ratio <= 1.40):
        raise ValueError(
            "gold splice boundary looks broken: "
            f"{last_wb} World Bank {world_bank[last_wb]:.2f}, "
            f"{first_tail} COMEX {comex[first_tail]:.2f}"
        )
    points: list[dict] = []
    for month in sorted(set(world_bank) | set(comex)):
        if month <= last_wb:
            if month in world_bank:
                points.append(
                    {"t": month, "v": world_bank[month], "source": "world_bank"}
                )
        elif month in comex:
            points.append({"t": month, "v": comex[month], "source": "comex"})
    meta = {
        "overlapMonths": len(overlap),
        "medianComexOverWorldBank": median,
        "lastWorldBankMonth": last_wb,
        "firstComexOnlyMonth": first_tail,
        "boundaryRatio": boundary_ratio,
    }
    return points, meta


def rebase_to(
    series: dict[str, float],
    base_month: str,
    *,
    level: float = 100.0,
) -> list[list[float | str]]:
    if base_month not in series:
        raise ValueError(f"base month {base_month} missing")
    base = series[base_month]
    if base == 0:
        raise ValueError(f"base month {base_month} is zero")
    return [
        [month, series[month] / base * level] for month in sorted(series)
    ]


def common_rebase(
    left: dict[str, float],
    right: dict[str, float],
    *,
    level: float = 100.0,
) -> tuple[str, list[list[float | str]], list[list[float | str]]]:
    """Rebase two series to 100 at their first shared month, on shared months only."""
    shared = sorted(set(left) & set(right))
    if not shared:
        raise ValueError("no overlap to rebase")
    base_month = shared[0]
    left_points = [
        [month, left[month] / left[base_month] * level] for month in shared
    ]
    right_points = [
        [month, right[month] / right[base_month] * level] for month in shared
    ]
    return base_month, left_points, right_points


def annual_average_ratio(
    monthly: dict[str, float],
    annual: dict[str, float],
    *,
    min_months: int = 6,
) -> list[list[float | str]]:
    """Average a monthly series within each year, then divide by that year's value."""
    buckets: dict[str, list[float]] = defaultdict(list)
    for month, value in monthly.items():
        buckets[month[:4]].append(value)
    points: list[list[float | str]] = []
    for year in sorted(buckets):
        if year not in annual:
            continue
        values = buckets[year]
        if len(values) < min_months:
            continue
        den = annual[year]
        if den == 0:
            continue
        points.append([year, (sum(values) / len(values)) / den])
    return points


def round_points(points: list, digits: int = 6) -> list:
    """Round numeric values so the JSON diff stays stable."""
    rounded = []
    for point in points:
        if isinstance(point, dict):
            item = dict(point)
            item["v"] = round(float(item["v"]), digits)
            rounded.append(item)
        else:
            month, value = point[0], point[1]
            if value is None:
                rounded.append([month, None])
            else:
                rounded.append([month, round(float(value), digits)])
    return rounded
