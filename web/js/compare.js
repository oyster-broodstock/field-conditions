// All sites side by side: latest values, and 7 days of water temperature and salinity.
import { COAST_COLOR, ago, el, header, load, num, timeChart } from "./common.js";

header("compare.html");
const main = document.getElementById("main");
const summary = await load("data/summary.json");
if (!summary) {
  main.replaceChildren(el("p", { class: "note" }, "No data yet. Run the ingest (see the README)."));
} else {
  const sites = summary.sites, colors = COAST_COLOR();
  const dashes = [undefined, [6, 3], [2, 3], [10, 3, 2, 3]];
  const seen = {};
  const style = (s) => { const i = (seen[s.coast] = (seen[s.coast] ?? -1) + 1); return { color: colors[s.coast], dash: dashes[i % dashes.length] }; };
  const tChart = el("div", { class: "chart" }), sChart = el("div", { class: "chart" });
  const cell = (x, d = 1, unit = "") => el("td", { class: "n", title: x ? `${x.station}${x.distance_km != null ? `, ${x.distance_km} km` : ""}` : "" }, x ? `${num(x.v, d)}${unit}` : "–");
  main.replaceChildren(
    el("section", { class: "card" }, el("h2", {}, "Latest readings", el("span", { class: "badge" }, ago(summary.generated_at))),
      el("div", { class: "scroll" }, el("table", {},
        el("thead", {}, el("tr", {}, el("th", {}, "Site"), el("th", {}, "Node"), el("th", { class: "n" }, "Water °C"), el("th", { class: "n" }, "Salinity"),
          el("th", { class: "n" }, "DO mg/L"), el("th", { class: "n" }, "Air °C"), el("th", { class: "n" }, "Rain 72 h mm"), el("th", { class: "n" }, "River m³/s"), el("th", {}, "Water station"))),
        el("tbody", {}, sites.map((s) => el("tr", {},
          el("td", {}, el("span", { class: `dot ${s.coast} ${s.kind}` }), el("a", { href: `site.html?id=${s.id}` }, s.name)),
          el("td", {}, s.node), cell(s.water_temp_c), cell(s.salinity_psu), cell(s.do_mgl), cell(s.air_temp_c),
          el("td", { class: "n" }, s.rain_72h_mm == null ? "–" : num(s.rain_72h_mm)), cell(s.discharge_cms, 0),
          el("td", { class: "small muted" }, s.water_temp_c ? `${s.water_temp_c.station} (${num(s.water_temp_c.distance_km, 0)} km)` : "none")))))),
      el("p", { class: "small muted" }, "Each value comes from the nearest public station that reports it, which can be tens of kilometres from the site. Open markers are hatcheries.")),
    el("section", { class: "card" }, el("h2", {}, "Water temperature, last 7 days"), tChart,
      el("p", { class: "small muted" }, "Colour is the coast (blue Atlantic, orange Gulf, teal Pacific); line style separates sites within a coast. Times in UTC.")),
    el("section", { class: "card" }, el("h2", {}, "Salinity, last 7 days"), sChart));
  const lines = (key) => { for (const k in seen) delete seen[k]; return sites.filter((s) => s[key]?.series?.length && s.kind === "field").map((s) => ({ label: s.name, data: s[key].series, ...style(s) })); };
  timeChart(tChart, lines("water_temp_c"), { unit: "°C", height: 320, legend: true });
  timeChart(sChart, lines("salinity_psu"), { unit: "PSU", height: 260, legend: true });
}
