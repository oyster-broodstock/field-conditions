// Shared helpers: data loading, formatting, page header, charts.

const cache = {};
export function load(path) {
  return (cache[path] ||= fetch(path, { cache: "no-cache" }).then((r) => (r.ok ? r.json() : null)).catch(() => null));
}
export const loadSites = () => load("sites.json").then((d) => d?.sites || []);

export const num = (v, d = 1) => (v == null || Number.isNaN(v) ? "–" : Number(v).toFixed(d));
export function ago(s) {
  if (!s) return "never";
  const min = Math.round((Date.now() - new Date(s)) / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  const h = Math.round(min / 60);
  return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} d ago`;
}
export const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
export const COAST_COLOR = () => ({ Atlantic: css("--atlantic"), Gulf: css("--gulf"), Pacific: css("--pacific") });
export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const REPO_URL = "https://github.com/oyster-broodstock/field-conditions";
export const archiveUrl = (siteId) => `${REPO_URL}/tree/data/archive/${encodeURIComponent(siteId)}`;

function bindResize(node, plot, height) {
  node._ro?.disconnect();
  if (typeof ResizeObserver === "undefined") return;
  const ro = new ResizeObserver(() => {
    const w = node.clientWidth;
    if (w > 0 && w !== plot.width) plot.setSize({ width: w, height });
  });
  ro.observe(node);
  node._ro = ro;
}

export function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k === "html") e.innerHTML = v;
    else if (v != null) e.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k != null) e.append(k.nodeType ? k : document.createTextNode(k));
  return e;
}
export const stat = (label, value) =>
  el("div", { class: "stat" }, el("div", { class: "label" }, label), el("div", { class: "value" }, value));

const NAV = [["index.html", "Map"], ["compare.html", "Compare"], ["baselines.html", "Baselines"], ["about.html", "Data"]];
export function header(current) {
  document.body.prepend(el("header", { class: "top" },
    el("h1", {}, "Oyster Broodstock CAP ", el("span", {}, "· field site conditions")),
    el("nav", {},
      NAV.map(([href, label]) => el("a", { href, "aria-current": href === current ? "page" : null }, label)),
      el("a", { href: "https://github.com/oyster-broodstock/field-conditions", target: "_blank", rel: "noopener" }, "GitHub"))));
  load("data/meta.json").then((m) => {  // local front-end work with ingest/tests/fake_api.py
    if (m?.synthetic) document.querySelector("header.top").after(el("div", { class: "banner" }, "Synthetic test data, not real observations"));
  });
}

// Line chart of one or more [[isoTime, value], ...] series on a shared time axis.
// opts: { tz, unit, height, bars } ; series: [{ label, data, color, dash }]
export function timeChart(node, series, opts = {}) {
  series = series.filter((s) => s.data?.length);
  if (!series.length) { node.replaceChildren(el("p", { class: "muted small" }, "No recent data.")); return null; }
  const times = [...new Set(series.flatMap((s) => s.data.map((p) => Date.parse(p[0]) / 1000)))].sort((a, b) => a - b);
  const idx = new Map(times.map((t, i) => [t, i]));
  const cols = series.map((s) => {
    const col = new Array(times.length).fill(null);
    for (const [t, v] of s.data) col[idx.get(Date.parse(t) / 1000)] = v;
    return col;
  });
  const palette = [css("--accent"), css("--accent-2"), css("--atlantic"), css("--good"), css("--bad")];
  const axis = { stroke: css("--muted"), grid: { stroke: css("--line") }, ticks: { stroke: css("--line") } };
  const now = Date.now() / 1000;
  const height = opts.height || 180;
  node.replaceChildren();
  const plot = new uPlot({
    width: node.clientWidth || 400, height,
    tzDate: (ts) => uPlot.tzDate(new Date(ts * 1e3), opts.tz || "UTC"),
    cursor: { y: false },
    legend: { show: series.length > 1 || !!opts.legend },
    scales: { x: { time: true } },
    axes: [axis, { ...axis, size: 46, label: opts.unit, labelSize: 16, font: "11px system-ui", labelFont: "11px system-ui" }],
    series: [{}, ...series.map((s, i) => ({
      label: s.label, stroke: s.color || palette[i % palette.length], width: 1.6, spanGaps: true, dash: s.dash,
      points: { show: false }, value: (u, v) => (v == null ? "–" : `${v} ${opts.unit || ""}`),
      ...(opts.bars ? { paths: uPlot.paths.bars({ size: [0.8, 12] }), fill: s.color || palette[i % palette.length] } : {}),
    }))],
    hooks: { draw: [(u) => {            // vertical "now" line when the chart spans past and future
      if (now < u.scales.x.min || now > u.scales.x.max) return;
      const x = u.valToPos(now, "x", true), { ctx, bbox } = u;
      ctx.save(); ctx.strokeStyle = css("--accent-2"); ctx.setLineDash([4, 4]); ctx.beginPath();
      ctx.moveTo(x, bbox.top); ctx.lineTo(x, bbox.top + bbox.height); ctx.stroke(); ctx.restore();
    }] },
  }, [times, ...cols], node);
  bindResize(node, plot, height);
  return plot;
}

// Monthly climatology: p05–p95 band of daily means, mean line, highest hourly value.
export function climatologyChart(node, monthly, height = 200) {
  const axis = { stroke: css("--muted"), grid: { stroke: css("--line") }, ticks: { stroke: css("--line") } };
  const x = monthly.map((m) => m.month);
  node.replaceChildren();
  const plot = new uPlot({
    width: node.clientWidth || 400, height, cursor: { y: false }, legend: { show: false },
    scales: { x: { time: false, range: [0.5, 12.5] } },
    axes: [{ ...axis, values: (u, v) => v.map((m) => MONTHS[m - 1] || ""), splits: () => x },
           { ...axis, size: 46, label: "°C", labelSize: 16, font: "11px system-ui", labelFont: "11px system-ui" }],
    series: [{ label: "Month", value: (u, v) => MONTHS[v - 1] || "" },
      { label: "p95 of daily means", stroke: "transparent", points: { show: false } },
      { label: "p05 of daily means", stroke: "transparent", points: { show: false } },
      { label: "Mean", stroke: css("--accent"), width: 2 },
      { label: "Highest hourly", stroke: css("--accent-2"), width: 0, points: { show: true, size: 6, fill: css("--accent-2") } }],
    bands: [{ series: [1, 2], fill: css("--accent") + "33" }],
  }, [x, monthly.map((m) => m.p95), monthly.map((m) => m.p05), monthly.map((m) => m.mean), monthly.map((m) => m.max_hourly)], node);
  bindResize(node, plot, height);
  return plot;
}

// Years with at least half the days present; partial years are shown but not used for headline numbers.
export const goodYears = (b) => (b?.annual || []).filter((a) => a.coverage >= 0.5);
export function baselineHeadline(b) {
  const yrs = goodYears(b);
  if (!yrs.length) return null;
  const top = (k) => yrs.reduce((m, a) => (a[k] > m[k] ? a : m));
  const med = (k) => { const v = yrs.map((a) => a[k]).sort((p, q) => p - q); return v[Math.floor(v.length / 2)]; };
  return { n: yrs.length, max7: top("max_7day_mean"), p99med: med("p99_hourly"), max7med: med("max_7day_mean"),
           warmMonth: b.monthly.reduce((m, x) => ((x.mean ?? -99) > (m.mean ?? -99) ? x : m)) };
}
