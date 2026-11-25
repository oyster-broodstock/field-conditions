// Historical water temperature at the station nearest each site: the numbers behind
// "how warm does it get here", for setting priming temperatures against local conditions.
import { baselineHeadline, climatologyChart, el, goodYears, header, load, loadSites, num } from "./common.js";

header("baselines.html");
const main = document.getElementById("main");
const sites = await loadSites();
const bases = await Promise.all(sites.map((s) => load(`baseline/${s.id}.json`)));
const rows = sites.map((s, i) => ({ s, b: bases[i], h: baselineHeadline(bases[i]) })).filter((x) => x.b);

if (!rows.length) {
  main.replaceChildren(el("p", { class: "note" }, "No baseline files yet. Run baseline/history.py (see the README)."));
} else {
  const th = rows[0].b.thresholds_c.filter((t) => t >= 25);
  const mean = (yrs, t) => (yrs.length ? yrs.reduce((a, y) => a + y.days_ge[t], 0) / yrs.length : null);
  const charts = [];
  main.replaceChildren(
    el("section", { class: "card" }, el("h2", {}, "Summer maxima by site", el("span", { class: "badge" }, `${rows[0].b.years[0]}–${rows[0].b.years[1]}`)),
      el("div", { class: "scroll" }, el("table", {},
        el("thead", {}, el("tr", {}, el("th", {}, "Site"), el("th", {}, "Station"), el("th", { class: "n" }, "Years"),
          el("th", { class: "n" }, "Warmest month mean"), el("th", { class: "n" }, "Typical peak (median 99th pct.)"),
          el("th", { class: "n" }, "Warmest 7-day mean"), th.map((t) => el("th", { class: "n" }, `Days/yr ≥ ${t}`)))),
        el("tbody", {}, rows.map(({ s, b, h }) => { const yrs = goodYears(b); return el("tr", {},
          el("td", {}, el("span", { class: `dot ${s.coast} ${s.kind}` }), el("a", { href: `site.html?id=${s.id}` }, s.name)),
          el("td", { class: "small" }, b.station.name), el("td", { class: "n" }, h ? h.n : 0),
          el("td", { class: "n" }, h ? num(h.warmMonth.mean) : "–"), el("td", { class: "n" }, h ? num(h.p99med) : "–"),
          el("td", { class: "n" }, h ? `${num(h.max7.max_7day_mean)} (${h.max7.year})` : "–"),
          th.map((t) => el("td", { class: "n" }, h ? num(mean(yrs, t), 0) : "–"))); })))),
      el("p", { class: "small muted" }, "All temperatures in °C, from hourly records at the nearest long-running public station, which is usually outside the site's own water body and deeper than an intertidal or floating-gear site. Treat these as the regional water mass, not the temperature oysters experience in gear. Years with less than half the days present are left out of these columns. Days per year count days whose maximum reached the threshold.")),
    el("div", { class: "grid2" }, rows.map(({ s, b }) => { const c = el("div", { class: "chart" }); charts.push(() => climatologyChart(c, b.monthly, 170));
      return el("section", { class: "card" }, el("h2", {}, s.name, el("span", { class: "badge" }, b.station.name)), c,
        el("details", { class: "small" }, el("summary", {}, "Yearly table"), el("div", { class: "scroll" }, el("table", {},
          el("thead", {}, el("tr", {}, el("th", {}, "Year"), el("th", { class: "n" }, "Coverage"), el("th", { class: "n" }, "Max hourly"), el("th", {}, "Date"), el("th", { class: "n" }, "99th pct."), el("th", { class: "n" }, "Max 7-day mean"))),
          el("tbody", {}, b.annual.map((a) => el("tr", {}, el("td", {}, a.year), el("td", { class: "n" }, `${Math.round(a.coverage * 100)}%`),
            el("td", { class: "n" }, num(a.max_hourly)), el("td", {}, a.max_date || ""), el("td", { class: "n" }, num(a.p99_hourly)), el("td", { class: "n" }, num(a.max_7day_mean))))))))); })),
    el("p", { class: "footer" }, "Band: 5th to 95th percentile of daily means for the month. Line: mean. Dots: highest single hourly value, screened only for plausibility (−2 to 40 °C), so isolated sensor spikes can appear; the 99th percentile and 7-day mean are the robust figures."));
  charts.forEach((d) => d());
}
