// One site: every public source, each labeled with its station and distance.
import { MONTHS, ago, baselineHeadline, climatologyChart, el, header, load, loadSites, num, stat, timeChart } from "./common.js";

header("");
const id = new URLSearchParams(location.search).get("id");
const main = document.getElementById("main");
const [sites, doc, base] = await Promise.all([loadSites(), load(`data/${id}.json`), load(`baseline/${id}.json`)]);
const site = sites.find((s) => s.id === id);

if (!site) {
  main.replaceChildren(el("p", {}, "Unknown site. ", el("a", { href: "index.html" }, "Back to the map")));
} else {
  document.title = `${site.name} · Oyster Broodstock CAP`;
  const tz = site.tz;
  const card = (title, badge, ...kids) => el("section", { class: "card" }, el("h2", {}, title, badge || ""), ...kids);
  const chartDiv = () => el("div", { class: "chart" });
  const fresh = (sec) => el("span", { class: "badge" }, sec?.fetched_at ? ago(sec.fetched_at) : "no data");
  const charts = [];  // drawn after the nodes are in the document, so widths are known

  main.replaceChildren(el("section", { class: "card" },
    el("h3", { style: "font-size:20px" }, el("span", { class: `dot ${site.coast} ${site.kind}` }), site.name),
    el("div", { class: "muted" }, `${site.kind === "field" ? "Field site" : "Hatchery"} · ${site.coast} coast · ${site.node} · `, el("i", {}, site.species)),
    el("p", { style: "margin:8px 0 0" }, site.context),
    site.gaps ? el("p", { class: "note small", style: "margin:10px 0 0" }, el("b", {}, "Known gaps. "), site.gaps) : null));

  if (!doc) main.append(el("p", { class: "note" }, "No data file for this site yet. Run the ingest (see the README)."));
  const grid = el("div", { class: "grid2" });
  main.append(grid);

  // ---- water: one card per variable, one line per station
  const stations = doc?.water?.stations || [];
  const VARS = [["water_temp_c", "Water temperature", "°C"], ["salinity_psu", "Salinity", "PSU"],
                ["do_mgl", "Dissolved oxygen", "mg/L"], ["ph", "pH", ""]];
  for (const [key, title, unit] of VARS) {
    const have = stations.filter((s) => s.variables?.includes(key));
    if (!have.length && key !== "water_temp_c" && key !== "salinity_psu") continue;
    const c = chartDiv();
    grid.append(card(title, fresh(doc?.water),
      have.length
        ? el("div", { class: "row" }, have.map((s) => stat(`${s.name} (${num(s.distance_km, 0)} km)`, `${num(s.latest?.[key], key === "ph" ? 2 : 1)} ${unit}`)))
        : el("p", { class: "muted small" }, `No public ${title.toLowerCase()} station is wired in for this site yet.`),
      c));
    if (have.length) charts.push(() => timeChart(c, have.map((s) => ({ label: s.name, data: s.series.filter((r) => r[key] != null).map((r) => [r.t, r[key]]) })), { tz, unit }));
    else c.remove();
  }
  const dead = stations.filter((s) => s.status !== "ok");
  const notes = stations.flatMap((s) => (s.notes || []).map((n) => `${s.name}: ${n}`));
  if (dead.length) main.append(el("p", { class: "small muted" }, "Not reporting: ", dead.map((s) => `${s.name} (${s.status})`).join(", ")));
  if (notes.length) main.append(el("p", { class: "small muted" }, notes.join(". ")));

  // ---- historical baseline
  if (base) {
    const h = baselineHeadline(base), c = chartDiv();
    const m = base.monthly[new Date().getMonth()];
    grid.append(card("Water temperature baseline", el("span", { class: "badge" }, `${base.years[0]}–${base.years[1]}`),
      h ? el("div", { class: "row" },
        stat(`Warmest 7-day mean (${h.max7.year})`, `${num(h.max7.max_7day_mean)} °C`),
        stat("Typical summer peak (median 99th pct.)", `${num(h.p99med)} °C`),
        stat(`${MONTHS[m.month - 1]} normal`, m.mean == null ? "–" : `${num(m.mean)} °C`)) : el("p", { class: "muted small" }, "Record too short for headline numbers."),
      c,
      el("p", { class: "small muted" }, `Hourly record at ${base.station.name}. Band: 5th to 95th percentile of daily means. Dots: highest single hourly value, screened only for plausibility. `,
        el("a", { href: "baselines.html" }, "All sites and yearly table"))));
    charts.push(() => climatologyChart(c, base.monthly));
  }

  // ---- tide
  if (doc?.tides) {
    const t = doc.tides, c = chartDiv();
    const next = t.hilo.filter((x) => Date.parse(x.t) > Date.now()).slice(0, 4);
    const f = new Intl.DateTimeFormat("en-US", { timeZone: tz, weekday: "short", hour: "numeric", minute: "2-digit" });
    grid.append(card("Tide (predicted)", fresh(t),
      el("div", { class: "small" }, next.map((x) => `${x.type === "H" ? "High" : "Low"} ${num(x.v, 2)} m ${f.format(new Date(x.t))}`).join(" · ")),
      c, el("p", { class: "small muted" }, `${t.station.name} (${t.station.id}), metres above MLLW, site local time.`)));
    charts.push(() => timeChart(c, [{ label: "Tide", data: t.curve }], { tz, unit: "m" }));
  }

  // ---- weather: observed then forecast air temperature
  if (doc?.observations || doc?.forecast) {
    const st = doc.observations?.stations?.[0], c = chartDiv();
    grid.append(card("Air temperature", fresh(doc.observations || doc.forecast),
      st ? el("div", { class: "row" }, stat(`${st.name} (${num(st.distance_km, 0)} km)`, `${num(st.latest.air_temp_c)} °C`),
        stat("Wind", st.latest.wind_ms == null ? "–" : `${num(st.latest.wind_ms)} m/s`)) : null,
      c, el("p", { class: "small muted" }, "Solid: observed. Dashed: NWS forecast for the site's grid cell.")));
    charts.push(() => timeChart(c, [
      { label: "Observed", data: (st?.series || []).filter((r) => r.air_temp_c != null).map((r) => [r.t, r.air_temp_c]) },
      { label: "Forecast", dash: [5, 4], data: (doc.forecast?.hourly || []).filter((r) => r.air_temp_c != null).map((r) => [r.t, r.air_temp_c]) }], { tz, unit: "°C" }));
  }

  // ---- rain
  if (doc?.rain) {
    const r = doc.rain, c = chartDiv();
    grid.append(card("Rain at the site", fresh(r),
      el("div", { class: "row" }, stat("24 h", `${num(r.totals_mm.h24)} mm`), stat("72 h", `${num(r.totals_mm.h72)} mm`), stat("7 days", `${num(r.totals_mm.h168)} mm`)),
      c, el("p", { class: "small muted" }, "NCEP Stage IV radar and gauge analysis at the site coordinates (about 4 km grid).")));
    charts.push(() => timeChart(c, [{ label: "Rain", data: r.hourly.map((x) => [x.t, x.precip_mm]) }], { tz, unit: "mm/h", bars: true }));
  }

  // ---- rivers
  const gauges = doc?.rivers?.gauges || [];
  if (gauges.length) {
    const c = chartDiv();
    grid.append(card("River discharge", fresh(doc.rivers),
      el("div", { class: "row" }, gauges.map((g) => stat(g.name, g.latest ? `${num(g.latest.discharge_cms, 0)} m³/s` : "–"))),
      c, el("p", { class: "small muted" }, "USGS provisional data. Freshwater inflow is the main driver of low-salinity events.")));
    charts.push(() => timeChart(c, gauges.map((g) => ({ label: g.name, data: g.series.map((x) => [x.t, x.discharge_cms]) })), { tz, unit: "m³/s" }));
  }

  main.append(el("p", { class: "footer" }, "Compiled from public sources for research coordination. Stations are often outside the site's own water body; check the distance on each card. ",
    el("a", { href: "about.html" }, "Sources and freshness")));
  charts.forEach((draw) => draw());
}
