import React, { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import { api } from "../../api.js";
import { useApp } from "../../App.jsx";
import { useCase } from "../../components/caseContext.js";
import { Empty, useAsync } from "../../components/ui.jsx";
import { TYPE_COLORS, yearOf } from "../../format.js";

export default function MapTab() {
  const { t } = useApp();
  const { caseId } = useCase();
  const [asOf, setAsOf] = useState("");
  const [hidden, setHidden] = useState([]);
  const data = useAsync(() => api.map(caseId, { as_of: asOf }), [caseId, asOf]);
  const d = data.data;
  const el = useRef(null);
  const map = useRef(null);
  const group = useRef(null);

  const range = useMemo(() => {
    const a = yearOf(d?.time_range?.from);
    const b = yearOf(d?.time_range?.to);
    return a !== null && b !== null && b > a ? [a, b] : null;
  }, [d?.time_range?.from, d?.time_range?.to]);

  useEffect(() => {
    if (!el.current || map.current) return undefined;
    map.current = L.map(el.current, { worldCopyJump: true }).setView([30, 10], 2);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18, attribution: "© <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> contributors",
    }).addTo(map.current);
    group.current = L.layerGroup().addTo(map.current);
    return () => { map.current.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    if (!map.current || !d) return;
    group.current.clearLayers();
    const points = [];
    d.layers.filter((layer) => !hidden.includes(layer.type)).forEach((layer) => {
      layer.features.forEach((f) => {
        const color = TYPE_COLORS[layer.type] || "#9fb0c3";
        const marker = L.circleMarker([f.lat, f.lon], { radius: 5 + Math.min(9, f.source_count * 2), color, fillColor: color, fillOpacity: 0.55, weight: 2 });
        const node = document.createElement("div");
        const title = document.createElement("strong");
        title.textContent = f.name;
        const meta = document.createElement("div");
        meta.textContent = `${t(`type_${layer.type}`)} · ${f.source_count} ${t("sources_word")}${f.date_start ? ` · ${f.date_start}${f.date_end ? `–${f.date_end}` : ""}` : ""}`;
        const link = document.createElement("a");
        link.href = `#/case/${caseId}/entities?open=${f.entity_id}`;
        link.textContent = t("open");
        node.append(title, meta, link);
        marker.bindPopup(node);
        marker.bindTooltip(f.name);
        marker.addTo(group.current);
        points.push([f.lat, f.lon]);
      });
    });
    if (points.length) map.current.fitBounds(points, { padding: [40, 40], maxZoom: 9 });
  }, [d, hidden, caseId, t]);

  const toggle = (type) => setHidden(hidden.includes(type) ? hidden.filter((x) => x !== type) : [...hidden, type]);
  const total = d ? d.layers.reduce((n, layer) => n + layer.count, 0) : 0;

  return (
    <div className="space-y-3">
      <div className="panel flex flex-wrap items-end gap-4">
        <label className="block">
          <span className="label">{t("as_of")}</span>
          <input className="field" style={{ width: 130 }} value={asOf} onChange={(e) => setAsOf(e.target.value)} placeholder="YYYY[-MM]" />
        </label>
        {range && (
          <label className="block min-w-[200px] flex-1">
            <span className="label">{t("time_slider")} ({asOf || range[1]})</span>
            <input type="range" className="w-full" min={range[0]} max={range[1]} value={yearOf(asOf) ?? range[1]} onChange={(e) => setAsOf(String(e.target.value))} aria-label={t("time_slider")} />
          </label>
        )}
        {asOf && <button type="button" className="btn btn-sm" onClick={() => setAsOf("")}>{t("clear")}</button>}
        <div className="flex flex-wrap gap-1.5">
          {(d?.layers || []).map((layer) => (
            <button key={layer.type} type="button" className={hidden.includes(layer.type) ? "btn btn-sm" : "btn btn-sm btn-active"} onClick={() => toggle(layer.type)}
              title={`${layer.source_count} ${t("sources_word")}${layer.coverage.from ? ` · ${layer.coverage.from}–${layer.coverage.to || ""}` : ""}`}>
              <span className="dot" style={{ background: TYPE_COLORS[layer.type] }} /> {t(`type_${layer.type}`)} ({layer.count})
            </button>
          ))}
        </div>
      </div>
      {data.error && <Empty>{data.error.message}</Empty>}
      {d && total === 0 && <Empty>{t("map_empty")}</Empty>}
      <div ref={el} style={{ height: 480, width: "100%" }} role="application" aria-label={t("tab_map")} data-testid="map" />
      <p className="help">{d?.attribution || "© OpenStreetMap contributors"}</p>
      {d && d.unplaced_count > 0 && (
        <p className="help">{t("unplaced", { n: d.unplaced_count })}: {d.unplaced.map((u) => u.name).join(", ")}</p>
      )}
    </div>
  );
}
