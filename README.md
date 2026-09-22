# Purchasing Power Lens

Charts-only companion to Daniel Rader’s Monetary Explainer, [The Debt-Based Monetary System for Everyday People](https://github.com/DRader150/The-Debt-Based-Monetary-System-for-Everyday-People).

The explainer is the prose: [drader150.github.io/The-Debt-Based-Monetary-System-for-Everyday-People](https://drader150.github.io/The-Debt-Based-Monetary-System-for-Everyday-People/).

This site is the pictures. It shows a life-cost strip in **dollars, gold ounces, or bitcoin**, plus a short set of monetary charts and teaching ratios. It does not track a personal economy, balances, holdings, or alerts.

After GitHub Pages is enabled, the site is [drader150.github.io/purchasing-power-lens](https://drader150.github.io/purchasing-power-lens/).

## GitHub Pages setup

The site is static files in `/docs` (no build step).

1. Open this repository on GitHub.
2. Go to **Settings → Pages**.
3. Under **Build and deployment**, set **Source** to **Deploy from a branch**.
4. Set the branch to **main** and the folder to **/docs**.
5. Save. Pages will publish `docs/index.html`.

The weekly data refresh (below) commits an updated `docs/data/series.json` to `main`. Pages serves that file as-is.

## What you can do on the page

- **Life-cost strip.** Oil (WTI), U.S. regular gasoline, U.S. diesel, residential electricity, a water/sewer/trash CPI, a defined food week, a new-vehicles CPI, and a televisions CPI.
- **Unit switch.** USD, gold ounces, or bitcoin. The switch divides the same monthly value by that month’s gold or bitcoin price. It does not draw a chart for every pair of units.
- **Monetary charts.** Median new-house price in gold and in bitcoin (Coinbase history only, from December 2014), gold vs the S&P 500, bitcoin in dollars on a log scale, and new-house price versus nominal median household income.
- **Teaching ratios.** Food week/gold, gas/oil, house/gold, house/bitcoin, gold/S&P, electricity vs wages, electricity vs CPI.

Starred cards are indexes or a constructed basket. The caveat is on the card and again under Sources.

## Data sources

Numbers are downloaded by `scripts/refresh_data.py` and saved in `docs/data/series.json` with a `generatedAt` timestamp. The page reads that file. It does not call FRED, BLS, or Yahoo from the browser (those endpoints are not reliable CORS sources for a public page).

| Series | What it is | Where it comes from |
| --- | --- | --- |
| WTI oil | Cushing, OK spot, $/barrel. Daily prices averaged by month. | [FRED DCOILWTICO](https://fred.stlouisfed.org/series/DCOILWTICO) (EIA) |
| Regular gasoline | U.S. regular, all formulations, $/gallon. Weekly prices averaged by month. | [FRED GASREGW](https://fred.stlouisfed.org/series/GASREGW) (EIA) |
| Diesel | U.S. diesel sales price, $/gallon. Weekly prices averaged by month. | [FRED GASDESW](https://fred.stlouisfed.org/series/GASDESW) (EIA) |
| Electricity | U.S. city-average residential price, $/kWh. | [FRED APU000072610](https://fred.stlouisfed.org/series/APU000072610) (BLS) |
| Water* | CPI-U water, sewer, **and trash collection**, seasonally adjusted. Not a gallon price. Starts 1997. | [FRED CUSR0000SEHG](https://fred.stlouisfed.org/series/CUSR0000SEHG) (BLS) |
| Food week* | Fixed basket below. Not an official USDA Food Plan. | BLS average prices via FRED. Recipe is on the page. |
| New vehicles* | CPI-U new vehicles, seasonally adjusted, 1982–84 = 100. Not a sticker price. | [FRED CUSR0000SETA01](https://fred.stlouisfed.org/series/CUSR0000SETA01) (BLS) |
| Televisions* | CPI-U televisions, not seasonally adjusted. Rebased so December 2024 = 100. Quality-adjusted; history includes pre-flat-panel sets. | [BLS CUUR0000SERA01](https://data.bls.gov/timeseries/CUUR0000SERA01) |
| Gold | London afternoon fix, monthly average, through the last month in the World Bank pink sheet (currently Dec 2024). Later months are the COMEX front-month futures close. The overlap was checked and the tail was **not** rescaled. | [World Bank commodity prices](https://www.worldbank.org/en/research/commodity-markets), then [Yahoo GC=F](https://finance.yahoo.com/quote/GC=F/) |
| Bitcoin | Coinbase daily price, averaged by month, from December 2014. Earlier prints are not used. | [FRED CBBTCUSD](https://fred.stlouisfed.org/series/CBBTCUSD) |
| S&P 500 | Price index, monthly close. Dividends are not included. Checked against FRED `SP500` (that FRED series itself is too short to chart alone). | [Yahoo ^GSPC](https://finance.yahoo.com/quote/%5EGSPC/) |
| New houses | Median sales price of **new** houses sold, not the existing-home median. | [FRED MSPNHSUS](https://fred.stlouisfed.org/series/MSPNHSUS) (Census / HUD) |
| Household income | Nominal median household income (not the real series `MEHOINUSA672N`). | [FRED MEHOINUSA646N](https://fred.stlouisfed.org/series/MEHOINUSA646N) |
| Hourly pay | Average hourly earnings, production and nonsupervisory, total private. | [FRED AHETPI](https://fred.stlouisfed.org/series/AHETPI) (BLS) |
| CPI | CPI-U all items and CPI-U electricity, for the electricity-vs-CPI chart. | [FRED CPIAUCSL](https://fred.stlouisfed.org/series/CPIAUCSL), [FRED CUSR0000SEHF01](https://fred.stlouisfed.org/series/CUSR0000SEHF01) |

FRED’s London gold series (`GOLDAMGBD228NLBM` / `GOLDPMGBD228NLBM`) no longer download from the public CSV endpoint, so they are not used.

The newest month of a daily or weekly series is an average of the days already published. The page marks that month “in progress.”

### Food week

One person’s reference intake for a week, aimed near 2,000 kcal/day, not a family grocery bill and not organic. Quantities are fixed. A month is plotted only when every ingredient has a published price. Nothing is carried forward.

| Item | FRED id | Quantity | Energy factor |
| --- | --- | --- | --- |
| Dried beans, any type | [APU0000714233](https://fred.stlouisfed.org/series/APU0000714233) | 2.0 lb | USDA black beans, raw, 341 kcal/100 g (stand-in for “any type”; other dry beans are about 337–347) |
| White all-purpose flour | [APU0000701111](https://fred.stlouisfed.org/series/APU0000701111) | 1.0 lb | 364 kcal/100 g |
| White pan bread | [APU0000702111](https://fred.stlouisfed.org/series/APU0000702111) | 1.0 lb | 266 kcal/100 g |
| Dry spaghetti and macaroni | [APU0000701322](https://fred.stlouisfed.org/series/APU0000701322) | 0.5 lb | 371 kcal/100 g |
| Eggs, grade A large | [APU0000708111](https://fred.stlouisfed.org/series/APU0000708111) | 1 dozen | 143 kcal/100 g × 50 g × 12 |
| Ground chuck | [APU0000703111](https://fred.stlouisfed.org/series/APU0000703111) | 1.0 lb | USDA 80% lean raw ground beef, 254 kcal/100 g, as a proxy for chuck |
| Whole fresh chicken | [APU0000706111](https://fred.stlouisfed.org/series/APU0000706111) | 2.0 lb | USDA broiler meat and skin, raw, 215 kcal/100 g. The BLS price includes bone, so edible kcal are lower. |
| Sliced bacon | [APU0000704111](https://fred.stlouisfed.org/series/APU0000704111) | 0.5 lb | USDA bacon, unprepared, 393 kcal/100 g (FDC 168277) |
| Bananas | [APU0000711211](https://fred.stlouisfed.org/series/APU0000711211) | 2.0 lb | 89 kcal/100 g |
| Field-grown tomatoes | [APU0000712311](https://fred.stlouisfed.org/series/APU0000712311) | 1.5 lb | 18 kcal/100 g |
| Whole milk | [APU0000709112](https://fred.stlouisfed.org/series/APU0000709112) | 0.5 gallon | 61 kcal/100 g; 244 g per cup; 16 cups per gallon |

Per-pound factors use the BLS pound of 453.6 g. The exact week total is stored in `series.json` as `foodBasket.kcalPerDay`.

White rice (`APU0000701312`) is **not** in the basket: the city average was unpublished from May 2000 through April 2002. Navel oranges (`APU0000711311`) are not in it either: that price is seasonal. Dried beans are the staple that actually publishes.

## How to refresh

From the repository root, with Python 3.11+ and no extra packages:

```bash
python3 scripts/test_series_math.py
python3 scripts/refresh_data.py
python3 scripts/validate_data.py
```

`refresh_data.py` writes `docs/data/series.json`. If a download is missing or a sanity check fails (gold splice far from 1, food cost absurd, CPI televisions join broken), the script exits and leaves the previous file untouched only if you still have it — a failed run does not write a new file, because the write happens after the checks inside `build()`.

GitHub Actions workflow `.github/workflows/refresh-data.yml` runs the same commands every Monday and on demand (**Actions → Refresh chart data → Run workflow**), then commits `docs/data/series.json` when it changed.

## Left out, with a reason

- **Car / food week.** No long public dollar series for the average new-car transaction price. The new-vehicles CPI is on the strip. Dividing an index by a dollar food cost would mix units, so the ratio is omitted.
- **Existing-home median.** FRED `HOSMEDUSM052N` did not return a long history from the public CSV endpoint (a short recent sample only). House charts use Census new-house prices (`MSPNHSUS`).
- **Official USDA food-plan dollar cost.** Those plans are spreadsheets and PDFs, not a stable keyless series.
- **FRED London gold fixes.** The public CSV endpoint no longer serves them.

Do not paste estimated history into `series.json` to fill a hole. Omit the series and say so.

## Out of scope

Personal economy tracking, balances, APRs, a holdings thesis, login, personal data, Excel dual-maintenance, custom portfolios, alerts, paywalls, and a chart for every pair of units.

## Reciprocal link

This site links to the explainer in the introduction and the footer. The explainer is a separate repository. Add this to that site’s footer so the link runs both ways:

```html
<a href="https://drader150.github.io/purchasing-power-lens/">Purchasing Power Lens (charts)</a>
```

## License of the chart library

`docs/js/chart.umd.min.js` is [Chart.js](https://www.chartjs.org/) (MIT). Series math and the page are in this repository.
