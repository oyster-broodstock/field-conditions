// Where the data comes from and how fresh each feed is, per site.
import { ago, archiveUrl, el, header, load, loadSites } from "./common.js";

header("about.html");
const main = document.getElementById("main");
const [sites, meta] = await Promise.all([loadSites(), load("data/meta.json")]);
const SOURCES = [["tides", "Tide"], ["water", "Water"], ["rivers", "Rivers"], ["observations", "Weather obs."], ["forecast", "Forecast"], ["rain", "Rain"]];
const badge = (st) => !st ? el("span", { class: "badge" }, "not run")
  : st.ok ? el("span", { class: "badge ok" }, ago(st.fetched_at))
  : el("span", { class: "badge bad", title: st.error }, st.using_previous ? `failed, showing ${ago(st.fetched_at)}` : "failed");
const link = (href, text) => el("a", { href, target: "_blank", rel: "noopener" }, text);

main.replaceChildren(
  el("section", { class: "card" }, el("h2", {}, "What this site is"),
    el("p", {}, "A compilation of public environmental data near the grow-out sites and hatcheries of the USDA NIFA project ",
      el("i", {}, "Strengthening U.S. Oyster Broodstock Systems"), " (award 2026-68012-47021). It exists so every node can see the same picture of conditions across the Atlantic, Gulf and Pacific sites, and so the public record is archived alongside the project's own measurements."),
    el("p", {}, "It is not a warning or advisory service and carries no harvest or closure information. Pins mark water bodies, not leases, and farms are not named."),
    el("p", { class: "small muted" }, "Every reading is labeled with its station and the distance from the site. Several sites have no public gauge in their own water body; the site pages say so under “Known gaps”. The project's own sondes and loggers will be added once deployed.")),
  el("section", { class: "card" }, el("h2", {}, "Feed status", el("span", { class: "badge" }, meta ? `run ${ago(meta.generated_at)}` : "no run yet")),
    el("div", { class: "scroll" }, el("table", {},
      el("thead", {}, el("tr", {}, el("th", {}, "Site"), SOURCES.map(([, t]) => el("th", {}, t)), el("th", {}, "Download"))),
      el("tbody", {}, sites.map((s) => el("tr", {}, el("td", {}, el("a", { href: `site.html?id=${s.id}` }, s.name)),
        SOURCES.map(([k]) => el("td", {}, badge(meta?.sites?.[s.id]?.[k]))),
        el("td", { class: "small" }, el("a", { href: `data/${s.id}.json` }, "JSON"), " · ", link(archiveUrl(s.id), "CSV")))))))),
  el("section", { class: "card" }, el("h2", {}, "Stations used"),
    el("div", { class: "scroll" }, el("table", {},
      el("thead", {}, el("tr", {}, el("th", {}, "Site"), el("th", {}, "Tide predictions"), el("th", {}, "Water"), el("th", {}, "River discharge"))),
      el("tbody", {}, sites.map((s) => el("tr", {}, el("td", {}, s.name),
        el("td", { class: "small" }, link(`https://tidesandcurrents.noaa.gov/stationhome.html?id=${s.tide.id}`, `${s.tide.name} (${s.tide.id})`)),
        el("td", { class: "small" }, [...s.coops.map((c) => [link(`https://tidesandcurrents.noaa.gov/stationhome.html?id=${c.id}`, `${c.name} (CO-OPS ${c.id})`), el("br")]),
          ...s.erddap.map((c) => [link(`https://erddap.sensors.ioos.us/erddap/tabledap/${c.id}.html`, c.name), el("br")])]),
        el("td", { class: "small" }, s.usgs.length ? s.usgs.map((g) => [link(`https://waterdata.usgs.gov/monitoring-location/${g.id}/`, `${g.name} (${g.id})`), el("br")]) : "none"))))))),
  el("section", { class: "card" }, el("h2", {}, "Sources"),
    el("ul", {},
      el("li", {}, link("https://tidesandcurrents.noaa.gov/", "NOAA CO-OPS"), ": tide predictions, water temperature, salinity."),
      el("li", {}, link("https://erddap.sensors.ioos.us/erddap/", "IOOS Sensors ERDDAP"), ": regional association platforms (CBIBS, CORMP, TAMU-CC Conrad Blucher Institute and others)."),
      el("li", {}, link("https://waterservices.usgs.gov/", "USGS Water Services"), ": river discharge (provisional)."),
      el("li", {}, link("https://www.weather.gov/documentation/services-web-api", "National Weather Service API"), ": surface observations and gridded forecast."),
      el("li", {}, link("https://mesonet.agron.iastate.edu/", "Iowa Environmental Mesonet"), ": NCEP Stage IV hourly precipitation analysis.")),
    el("p", { class: "small muted" }, "Updated hourly by a GitHub Actions workflow. Every observation is also appended to a permanent archive (the ", link("https://github.com/oyster-broodstock/field-conditions/tree/data", "data branch"), "), one CSV per site per year. Source code and station configuration are in the ", link("https://github.com/oyster-broodstock/field-conditions", "repository"), ".")));
