/* Purchasing Power Lens — render baked public series. No network except series.json. */

(function () {
  const HELP = {
    usd: "Showing the published unit. Dollars for prices, index points for the starred CPI series.",
    gold: "Each value divided by that month’s gold price (USD per troy ounce). A lower line means it took less gold. Index cards become index points per ounce, which is not a shelf price.",
    btc: "Each value divided by that month’s bitcoin price. Bitcoin starts in December 2014 (Coinbase on FRED). Earlier months drop off. Index cards become index points per bitcoin, not a price tag.",
  };

  const LIFE_COLOR = {
    oil: "#e4c27a",
    gasoline: "#8eb7e8",
    diesel: "#e2a07a",
    electricity: "#f0dc8a",
    water: "#7ec8c3",
    food: "#a3cf8c",
    vehicles: "#d7b0e8",
    televisions: "#f0b0c4",
  };

  const SERIES_COLORS = ["#e4c27a", "#8eb7e8", "#e2a07a", "#a3cf8c", "#d7b0e8"];
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  const charts = [];
  let data = null;
  let goldByMonth = new Map();
  let btcByMonth = new Map();
  let unit = "usd";

  function monthNumber(label) {
    if (label.length === 4) return Number(label);
    const [year, month] = label.split("-").map(Number);
    return year + (month - 1) / 12;
  }

  function monthsBetween(a, b) {
    const [ay, am] = a.split("-").map(Number);
    const [by, bm] = b.split("-").map(Number);
    return (by - ay) * 12 + (bm - am);
  }

  function expand(points) {
    const out = [];
    for (let i = 0; i < points.length; i += 1) {
      const [label, value] = points[i];
      if (i > 0 && label.length > 4 && points[i - 1][0].length > 4) {
        if (monthsBetween(points[i - 1][0], label) > 1) {
          out.push({ x: monthNumber(label) - 1 / 12, y: null, label: "" });
        }
      }
      out.push({ x: monthNumber(label), y: value, label });
    }
    return out;
  }

  function formatNum(value) {
    if (value == null || Number.isNaN(value)) return "";
    const abs = Math.abs(value);
    if (abs === 0) return "0";
    if (abs >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
    if (abs >= 100) return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
    if (abs >= 1) return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
    if (abs >= 0.01) return value.toLocaleString(undefined, { maximumFractionDigits: 4 });
    const digits = Math.min(8, Math.max(2, Math.ceil(-Math.log10(abs)) + 2));
    return value.toLocaleString(undefined, { maximumFractionDigits: digits });
  }

  function formatLatest(item, value) {
    const text = formatNum(value);
    if (unit === "usd" && item.kind === "dollars") return `$${text}`;
    return text;
  }

  function prettyWhen(label) {
    if (!label) return "";
    if (label.length === 4) return label;
    const [year, month] = label.split("-");
    return `${MONTHS[Number(month) - 1]} ${year}`;
  }

  function yLabel(item) {
    if (item.kind === "index") {
      if (unit === "usd") return "index points";
      if (unit === "gold") return "index points per troy oz";
      return "index points per bitcoin";
    }
    if (unit === "usd") return item.usdUnit;
    if (unit === "gold") return `troy oz per ${item.per}`;
    return `bitcoin per ${item.per}`;
  }

  function convert(points) {
    if (unit === "usd") return points;
    const table = unit === "gold" ? goldByMonth : btcByMonth;
    const out = [];
    points.forEach(([label, value]) => {
      const divisor = table.get(label);
      if (divisor) out.push([label, value / divisor]);
    });
    return out;
  }

  function destroyCharts() {
    while (charts.length) charts.pop().destroy();
  }

  function xExtent(seriesList) {
    let min = Infinity;
    let max = -Infinity;
    seriesList.forEach((series) => {
      series.points.forEach(([label]) => {
        if (!label) return;
        const x = monthNumber(label);
        if (x < min) min = x;
        if (x > max) max = x;
      });
    });
    if (!Number.isFinite(min) || !Number.isFinite(max)) return { min: 1960, max: 2026 };
    if (max - min < 0.25) {
      min -= 0.5;
      max += 0.5;
    }
    return { min, max };
  }

  function baseOptions(log, xMin, xMax) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title(items) {
              const label = items[0] && items[0].raw && items[0].raw.label;
              return label ? prettyWhen(label) : "";
            },
            label(context) {
              if (context.parsed.y == null) return "";
              const name = context.dataset.label ? `${context.dataset.label}: ` : "";
              return name + formatNum(context.parsed.y);
            },
          },
        },
      },
      scales: {
        x: {
          type: "linear",
          min: xMin,
          max: xMax,
          ticks: {
            maxTicksLimit: 6,
            color: "#b7ad9c",
            callback(value) {
              const year = Math.floor(value + 1e-6);
              if (year < Math.floor(xMin) || year > Math.ceil(xMax)) return "";
              return String(year);
            },
          },
          grid: { color: "rgba(243,239,230,0.06)" },
        },
        y: {
          type: log ? "logarithmic" : "linear",
          ticks: {
            maxTicksLimit: 6,
            color: "#b7ad9c",
            callback(value) { return formatNum(value); },
          },
          grid: { color: "rgba(243,239,230,0.06)" },
        },
      },
    };
  }

  function draw(canvas, seriesList, log) {
    const datasets = seriesList.map((series, index) => ({
      label: series.name,
      data: expand(series.points),
      borderColor: series.color || SERIES_COLORS[index % SERIES_COLORS.length],
      backgroundColor: series.color || SERIES_COLORS[index % SERIES_COLORS.length],
      borderWidth: 1.75,
      borderDash: series.dash ? [5, 4] : [],
      pointRadius: 0,
      pointHitRadius: 12,
      tension: 0,
      spanGaps: false,
    }));
    const extent = xExtent(seriesList);
    const chart = new Chart(canvas, {
      type: "line",
      data: { datasets },
      options: baseOptions(log, extent.min, extent.max),
    });
    charts.push(chart);
    return chart;
  }

  function legend(seriesList) {
    if (seriesList.length < 2) return "";
    const bits = seriesList.map((series, index) => {
      const color = series.color || SERIES_COLORS[index % SERIES_COLORS.length];
      return `<span><i class="swatch" style="background:${color}"></i>${series.name}</span>`;
    });
    return `<p class="legend">${bits.join("")}</p>`;
  }

  function renderLife() {
    const grid = document.getElementById("life-grid");
    const generatedMonth = data.generatedAt.slice(0, 7);
    grid.innerHTML = data.life.map((item) => {
      const converted = convert(item.points);
      const last = converted[converted.length - 1];
      const partial = last && last[0] === generatedMonth ? " · month in progress" : "";
      const indexClass = item.kind === "index" ? " is-index" : "";
      const empty = last
        ? `<p class="latest"><span class="num">${formatLatest(item, last[1])}</span><span class="unit">${yLabel(item)}</span></p>
           <p class="when">${prettyWhen(last[0])}${partial}</p>`
        : `<p class="when">No overlap with ${unit === "gold" ? "gold" : "bitcoin"} yet.</p>`;
      return `<article class="card${indexClass}" id="life-${item.id}">
        <h3>${item.title}</h3>
        ${empty}
        <div class="chart-box"><canvas id="canvas-${item.id}" aria-label="${item.title}" role="img"></canvas></div>
        <p class="caveat">${item.caveat}</p>
        <p class="source"><a href="${item.sourceUrl}">${item.source}</a></p>
      </article>`;
    }).join("");

    data.life.forEach((item) => {
      const converted = convert(item.points);
      const canvas = document.getElementById(`canvas-${item.id}`);
      if (!converted.length) return;
      draw(canvas, [{
        name: item.title,
        points: converted,
        color: LIFE_COLOR[item.id] || SERIES_COLORS[0],
      }], item.id === "televisions");
    });
    document.getElementById("unit-help").textContent = HELP[unit];
  }

  function renderStack(sectionId, gridId) {
    const grid = document.getElementById(gridId);
    const items = data.charts.filter((chart) => chart.section === sectionId);
    grid.innerHTML = items.map((chart) => `
      <article class="card" id="chart-${chart.id}">
        <h3>${chart.title}</h3>
        <p class="caveat">${chart.subtitle}</p>
        ${legend(chart.series)}
        <div class="chart-box"><canvas id="canvas-${chart.id}" aria-label="${chart.title}" role="img"></canvas></div>
        <p class="source"><a href="${chart.sourceUrl}">${chart.source}</a></p>
      </article>
    `).join("");
    items.forEach((chart) => {
      draw(
        document.getElementById(`canvas-${chart.id}`),
        chart.series,
        Boolean(chart.log),
      );
    });
  }

  function renderSources() {
    const seen = new Set();
    const rows = [];
    function add(name, url, used) {
      const key = `${name}|${url}`;
      if (seen.has(key)) return;
      seen.add(key);
      rows.push({ name, url, used });
    }
    data.gold.sources.forEach((source) => add(source.name, source.url, "Gold price"));
    add(data.btc.source, data.btc.sourceUrl, "Bitcoin price");
    data.life.forEach((item) => add(item.source, item.sourceUrl, item.title));
    data.charts.forEach((chart) => add(chart.source, chart.sourceUrl, chart.title));

    document.getElementById("source-list").innerHTML = `
      <div class="source-block">
        <table>
          <thead><tr><th>Used for</th><th>Source</th></tr></thead>
          <tbody>
            ${rows.map((row) => `<tr><td>${row.used}</td><td><a href="${row.url}">${row.name}</a></td></tr>`).join("")}
          </tbody>
        </table>
      </div>
      <p class="caveat">${data.gold.caveat} Overlap check: ${data.gold.splice.overlapMonths} shared months, median COMEX ÷ World Bank = ${data.gold.splice.medianComexOverWorldBank}. Splice after ${data.gold.splice.lastWorldBankMonth} (next month was ${data.gold.splice.boundaryRatio}× the fix, left unscaled).</p>
      <p class="caveat">${data.btc.caveat}</p>
      <p class="caveat">S&amp;P check for ${data.checks.sp500.month}: Yahoo monthly close ${data.checks.sp500.yahooMonthlyClose.toLocaleString()} versus the FRED SP500 monthly mean ${data.checks.sp500.fredMonthlyMean.toLocaleString()} (ratio ${data.checks.sp500.ratio}).</p>
    `;

    const basket = data.foodBasket;
    document.getElementById("recipe").innerHTML = `
      <h3>Food-week recipe</h3>
      <p class="caveat">About ${basket.kcalPerDay.toLocaleString()} kcal/day (${basket.kcalPerWeek.toLocaleString()} kcal in the week) using the energy factors below. Latest complete month ${prettyWhen(basket.latestMonth)} cost $${basket.latestCost.toFixed(2)}. Energy factors are USDA reference values applied to BLS selling units, not a lab test of the CPI sample.</p>
      <div class="recipe">
        <table>
          <thead><tr><th>Item</th><th>Qty</th><th class="numcell">Latest price</th><th class="numcell">Line</th><th>Energy factor</th></tr></thead>
          <tbody>
            ${basket.recipe.map((item) => `<tr>
              <td><a href="${item.fredUrl}">${item.name}</a><br><span class="when">${item.seriesId}</span></td>
              <td>${item.qty} ${item.qtyUnit}</td>
              <td class="numcell">$${item.latestPrice.toFixed(3)}</td>
              <td class="numcell">$${item.latestLineCost.toFixed(2)}</td>
              <td>${item.energyNote}</td>
            </tr>`).join("")}
          </tbody>
        </table>
      </div>
    `;

    const omitted = document.getElementById("omitted");
    omitted.innerHTML = `<h3>Left off on purpose</h3><ul>${
      data.omitted.map((item) => `<li><strong>${item.name}.</strong> ${item.reason}</li>`).join("")
    }</ul>`;
  }

  function setUnit(next, pushUrl) {
    unit = next;
    document.querySelectorAll(".unit-toggle button").forEach((button) => {
      button.setAttribute("aria-pressed", button.dataset.unit === unit ? "true" : "false");
    });
    if (pushUrl) {
      const url = new URL(window.location.href);
      if (unit === "usd") url.searchParams.delete("unit");
      else url.searchParams.set("unit", unit);
      window.history.replaceState({}, "", url);
    }
    destroyCharts();
    renderLife();
    renderStack("monetary", "monetary-grid");
    renderStack("ratios", "ratio-grid");
  }

  function bindToggle() {
    document.querySelectorAll(".unit-toggle button").forEach((button) => {
      button.addEventListener("click", () => setUnit(button.dataset.unit, true));
    });
  }

  async function init() {
    bindToggle();
    try {
      const response = await fetch("data/series.json");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      data = await response.json();
    } catch (error) {
      document.getElementById("refreshed").innerHTML = `<span class="error">Could not load chart data (${error.message}).</span>`;
      return;
    }
    goldByMonth = new Map(data.gold.points);
    btcByMonth = new Map(data.btc.points);
    Chart.defaults.color = "#b7ad9c";
    Chart.defaults.font.family = '"Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif';
    const when = new Date(data.generatedAt);
    const stamp = Number.isNaN(when.getTime())
      ? data.generatedAt
      : when.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
    document.getElementById("refreshed").textContent = `Data baked ${stamp} UTC. Prices are nominal unless a chart says it is rebased.`;
    renderSources();
    const requested = new URLSearchParams(window.location.search).get("unit");
    setUnit(requested === "gold" || requested === "btc" ? requested : "usd", false);
  }

  init();
})();
