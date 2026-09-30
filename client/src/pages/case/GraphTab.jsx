import React, { useEffect, useMemo, useRef, useState } from "react";
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from "d3-force";
import { api } from "../../api.js";
import { go, useApp } from "../../App.jsx";
import { useCase } from "../../components/caseContext.js";
import { Empty, Field, StatusChip, useAsync } from "../../components/ui.jsx";
import { STATUSES, STATUS_HEX, TYPE_COLORS } from "../../format.js";

const W = 900;
const H = 560;

// The layout is settled off-screen (a fixed number of ticks) and then fitted to the canvas, so the first paint is already tidy.
function useLayout(graph) {
  const [layout, setLayout] = useState({ pos: {}, fit: { x: 0, y: 0, k: 1 } });
  useEffect(() => {
    if (!graph) return;
    const nodes = graph.nodes.map((n) => ({ ...n }));
    const links = graph.edges.map((e) => ({ ...e }));
    const n = nodes.length;
    const sim = forceSimulation(nodes)
      .force("link", forceLink(links).id((d) => d.id).distance(n < 12 ? 190 : 140).strength(0.4))
      .force("charge", forceManyBody().strength(n < 12 ? -900 : -500))
      .force("collide", forceCollide(46))
      .force("center", forceCenter(W / 2, H / 2))
      .force("gx", forceX(W / 2).strength(0.12))
      .force("gy", forceY(H / 2).strength(0.16))
      .stop();
    for (let i = 0; i < 400; i += 1) sim.tick();
    const xs = nodes.map((d) => d.x);
    const ys = nodes.map((d) => d.y);
    const pad = 90;
    const minX = Math.min(...xs) - pad, maxX = Math.max(...xs) + pad, minY = Math.min(...ys) - pad, maxY = Math.max(...ys) + pad;
    const k = Math.min(1.6, W / (maxX - minX), H / (maxY - minY));
    const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
    setLayout({ pos: Object.fromEntries(nodes.map((d) => [d.id, [d.x, d.y]])), fit: { x: W / 2 - cx * k, y: H / 2 - cy * k, k } });
  }, [graph]);
  return layout;
}

const short = (text, n = 22) => (text.length > n ? `${text.slice(0, n - 1)}…` : text);

export default function GraphTab() {
  const { t } = useApp();
  const { caseId } = useCase();
  const [entityId, setEntityId] = useState("");
  const [depth, setDepth] = useState(1);
  const [statuses, setStatuses] = useState(["claimed", "corroborated", "confirmed", "disputed", "unsupported"]);
  const [asOf, setAsOf] = useState("");
  const [sel, setSel] = useState(null);
  const ents = useAsync(() => api.entities(caseId, { limit: 200 }), [caseId]);
  const data = useAsync(
    () => api.graph(caseId, { entity_id: entityId, depth, status: statuses.join(","), as_of: asOf, include_retracted: statuses.includes("retracted") }),
    [caseId, entityId, depth, statuses.join(","), asOf],
  );
  const g = data.data;
  const { pos, fit } = useLayout(g);
  const byId = useMemo(() => Object.fromEntries((g?.nodes || []).map((n) => [n.id, n])), [g]);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  useEffect(() => { setView(fit); }, [fit]);
  const drag = useRef(null);
  const toggle = (s) => setStatuses(statuses.includes(s) ? statuses.filter((x) => x !== s) : [...statuses, s]);
  const edge = g?.edges.find((e) => e.id === sel?.edge);
  const node = byId[sel?.node];
  const linked = new Set(node ? g.edges.filter((e) => e.source === node.id || e.target === node.id).flatMap((e) => [e.source, e.target]) : []);

  return (
    <div className="space-y-3">
      <div className="panel grid gap-3 md:grid-cols-4">
        <Field label={t("center_on")}>
          <select className="field" value={entityId} onChange={(e) => setEntityId(e.target.value)}>
            <option value="">{t("whole_case")}</option>
            {(ents.data?.items || []).map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
          </select>
        </Field>
        <Field label={t("depth")}><input className="field" type="number" min="1" max="4" disabled={!entityId} value={depth} onChange={(e) => setDepth(Number(e.target.value) || 1)} /></Field>
        <Field label={t("as_of")}><input className="field" value={asOf} onChange={(e) => setAsOf(e.target.value)} placeholder="YYYY[-MM]" /></Field>
        <div className="flex items-end"><button type="button" className="btn btn-sm" onClick={() => setView(fit)}>{t("reset_view")}</button></div>
        <div className="flex flex-wrap gap-1.5 md:col-span-4">
          {STATUSES.map((s) => (
            <button key={s} type="button" className={statuses.includes(s) ? "btn btn-sm btn-active" : "btn btn-sm"} onClick={() => toggle(s)}>
              <span className="dot" style={{ background: STATUS_HEX[s] }} /> {t(`status_${s}`)}
            </button>
          ))}
        </div>
      </div>
      {data.error && <Empty>{data.error.message}</Empty>}
      {g && g.nodes.length === 0 && <Empty>{t("graph_empty")}</Empty>}
      {g && g.nodes.length > 0 && (
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_260px]">
          <div className="panel p-0" style={{ overflow: "hidden" }}>
            <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block", background: "#0a120e", touchAction: "none", cursor: "grab" }} role="img" aria-label={t("tab_graph")} data-testid="graph"
              onWheel={(e) => { setView((v) => ({ ...v, k: Math.min(3, Math.max(0.4, v.k * (e.deltaY < 0 ? 1.1 : 0.9))) })); }}
              onPointerDown={(e) => { drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y }; e.currentTarget.setPointerCapture(e.pointerId); }}
              onPointerMove={(e) => { if (drag.current) setView((v) => ({ ...v, x: drag.current.vx + (e.clientX - drag.current.x), y: drag.current.vy + (e.clientY - drag.current.y) })); }}
              onPointerUp={() => { drag.current = null; }}>
              <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
                {g.edges.map((e) => {
                  const a = pos[e.source];
                  const b = pos[e.target];
                  if (!a || !b) return null;
                  const active = sel?.edge === e.id;
                  return (
                    <g key={e.id} onClick={(ev) => { ev.stopPropagation(); setSel({ edge: e.id }); }} style={{ cursor: "pointer" }}>
                      <line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke={STATUS_HEX[e.status]} strokeWidth={active ? 4 : 1.5 + Math.min(3, e.evidence_count * 0.6)}
                        strokeDasharray={e.status === "claimed" || e.status === "unsupported" ? "5 4" : undefined} opacity={e.status === "retracted" ? 0.4 : 0.85} />
                      <line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="transparent" strokeWidth="12"><title>{e.label}</title></line>
                      <text x={(a[0] + b[0]) / 2} y={(a[1] + b[1]) / 2 - 3} fontSize="9" textAnchor="middle" fill="#8aa397">{short(e.label, 34)}</text>
                    </g>
                  );
                })}
                {g.nodes.map((n) => {
                  const p = pos[n.id];
                  if (!p) return null;
                  const dim = node && n.id !== node.id && !linked.has(n.id);
                  return (
                    <g key={n.id} transform={`translate(${p[0]} ${p[1]})`} onClick={(ev) => { ev.stopPropagation(); setSel({ node: n.id }); }} style={{ cursor: "pointer" }} opacity={dim ? 0.3 : 1}>
                      <circle r={8 + Math.min(10, n.degree * 1.5)} fill={TYPE_COLORS[n.type] || "#9fb0c3"} fillOpacity={n.private ? 0.25 : 0.8} stroke={n.center ? "#fff" : "#0c1812"} strokeWidth={n.center ? 3 : 1.5} strokeDasharray={n.private ? "3 2" : undefined} />
                      <text y={-(12 + Math.min(10, n.degree * 1.5))} fontSize="12" textAnchor="middle" fill="#e6efe9" style={{ paintOrder: "stroke" }} stroke="#0a120e" strokeWidth="3">{short(n.name)}</text>
                      <title>{n.name}</title>
                    </g>
                  );
                })}
              </g>
            </svg>
          </div>
          <aside className="panel space-y-2 text-[13px]">
            {!node && !edge && (
              <>
                <div className="help">{t("graph_hint")}</div>
                <div className="flex flex-col gap-1">{STATUSES.map((s) => <StatusChip key={s} status={s} t={t} />)}</div>
                <div className="flex flex-wrap gap-2 pt-1">{Object.entries(TYPE_COLORS).map(([k, c]) => <span key={k} className="help"><span className="dot" style={{ background: c }} /> {t(`type_${k}`)}</span>)}</div>
                <div className="help pt-1">{g.nodes.length} {t("entities_word")} · {g.edges.length} {t("relations_word")}{g.truncated ? ` · ${t("truncated_graph")}` : ""}</div>
              </>
            )}
            {node && (
              <>
                <div className="font-semibold">{node.name}</div>
                <div className="help">{t(`type_${node.type}`)} · {node.source_count} {t("sources_word")}</div>
                <div className="flex gap-2">
                  <button type="button" className="btn btn-sm" onClick={() => { setEntityId(String(node.id)); setSel(null); }}>{t("center_here")}</button>
                  <button type="button" className="btn btn-sm" onClick={() => go(`case/${caseId}/entities?open=${node.id}`)}>{t("open")}</button>
                </div>
              </>
            )}
            {edge && (
              <>
                <div className="font-semibold">{edge.label}</div>
                <StatusChip status={edge.status} t={t} />
                <div className="help">{edge.evidence_count} {t("evidence_word")} · {edge.cite}</div>
                {(edge.valid_from || edge.valid_to) && <div className="help">{edge.valid_from || "?"} – {edge.valid_to || "…"}</div>}
                {edge.flags.map((f) => <div key={f} className="chip chip-amber">{f}</div>)}
                <button type="button" className="btn btn-sm" onClick={() => go(`case/${caseId}/relations?status=${edge.status}`)}>{t("open")}</button>
              </>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
