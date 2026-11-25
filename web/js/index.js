// Map of all sites plus a list with the latest public readings near each.
import { COAST_COLOR, ago, el, header, load, loadSites, num } from "./common.js";

header("index.html");
const [sites, summary] = await Promise.all([loadSites(), load("data/summary.json")]);
const latest = Object.fromEntries((summary?.sites || []).map((s) => [s.id, s]));
const colors = COAST_COLOR();

const map = new maplibregl.Map({
  container: "map",
  style: { version: 8, sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
    tileSize: 256, maxzoom: 19, attribution: "© OpenStreetMap contributors" } },
    layers: [{ id: "osm", type: "raster", source: "osm" }] },
  bounds: [[-126, 25], [-73, 49.5]], fitBoundsOptions: { padding: 30 },
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");

const reading = (s) => {
  const L = latest[s.id] || {};
  const bits = [];
  if (L.water_temp_c) bits.push(`Water ${num(L.water_temp_c.v)} °C`);
  if (L.salinity_psu) bits.push(`salinity ${num(L.salinity_psu.v)}`);
  if (L.air_temp_c) bits.push(`air ${num(L.air_temp_c.v)} °C`);
  return bits.join(" · ") || "No current readings";
};

for (const s of sites) {
  const dot = el("div", { title: s.name, style:
    `width:16px;height:16px;border-radius:50%;cursor:pointer;border:3px solid ${colors[s.coast]};` +
    `background:${s.kind === "field" ? colors[s.coast] : "#fff"};box-shadow:0 0 0 2px rgba(255,255,255,.9)` });
  const popup = el("div", {},
    el("b", {}, s.name), el("br"),
    el("span", { class: "muted" }, `${s.kind === "field" ? "Field site" : "Hatchery"} · ${s.node}`), el("br"),
    reading(s), el("br"),
    el("a", { href: `site.html?id=${encodeURIComponent(s.id)}` }, "Open site page"));
  new maplibregl.Marker({ element: dot }).setLngLat([s.lon, s.lat])
    .setPopup(new maplibregl.Popup({ offset: 12 }).setDOMContent(popup))
    .addTo(map);
}

const panel = document.getElementById("panel");
panel.replaceChildren(
  el("p", { class: "small muted" }, "Public environmental data near each field site and hatchery. Filled markers are grow-out sites; open markers are hatcheries. Pins mark the water body, not a lease. ",
    summary ? `Updated ${ago(summary.generated_at)}.` : "No data file yet; run the ingest."));
for (const [kind, title] of [["field", "Field sites"], ["hatchery", "Hatcheries and broodstock facilities"]]) {
  panel.append(el("h2", { class: "group" }, title));
  for (const s of sites.filter((x) => x.kind === kind)) {
    const L = latest[s.id] || {};
    const wt = L.water_temp_c;
    panel.append(el("a", { class: "site", href: `site.html?id=${s.id}` }, el("section", { class: "card" },
      el("h3", {}, el("span", { class: `dot ${s.coast} ${s.kind}` }), s.name),
      el("div", { class: "small muted" }, `${s.coast} · ${s.node}`),
      el("div", { class: "row", style: "margin-top:6px" },
        el("div", { class: "stat" }, el("div", { class: "label" }, "Water"), el("div", { class: "value" }, wt ? `${num(wt.v)} °C` : "–")),
        el("div", { class: "stat" }, el("div", { class: "label" }, "Salinity"), el("div", { class: "value" }, L.salinity_psu ? num(L.salinity_psu.v) : "–")),
        el("div", { class: "stat" }, el("div", { class: "label" }, "Air"), el("div", { class: "value" }, L.air_temp_c ? `${num(L.air_temp_c.v)} °C` : "–")),
        el("div", { class: "stat" }, el("div", { class: "label" }, "Rain 72 h"), el("div", { class: "value" }, L.rain_72h_mm != null ? `${num(L.rain_72h_mm)} mm` : "–"))),
      wt ? el("div", { class: "small muted" }, `Water from ${wt.station}, ${num(wt.distance_km, 0)} km away, ${ago(wt.t)}`) : null)));
  }
}
