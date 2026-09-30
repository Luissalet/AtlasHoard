import React, { useState } from "react";
import { api } from "../../api.js";
import { useApp } from "../../App.jsx";
import { useCase } from "../../components/caseContext.js";
import { ConfirmButton, Drawer, Empty, Field, PrivateChip, Section, StatusChip, useAsync } from "../../components/ui.jsx";
import { ENTITY_TYPES, TYPE_COLORS } from "../../format.js";

function TypeDot({ type }) {
  return <span className="dot" style={{ background: TYPE_COLORS[type] || "var(--muted)" }} />;
}

function EntityForm({ initial, onSubmit, onCancel, submitLabel }) {
  const { t } = useApp();
  const [f, setF] = useState({ type: "organization", name: "", aliases: "", description: "", lat: "", lon: "", date_start: "", date_end: "", public_figure: false, ...initial });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const submit = (e) => {
    e.preventDefault();
    const body = { type: f.type, name: f.name, description: f.description, public_figure: f.type === "person" ? f.public_figure : undefined };
    if (f.aliases.trim()) body.aliases = f.aliases.split(",").map((s) => s.trim()).filter(Boolean);
    if (f.lat !== "" && f.lon !== "") { body.lat = Number(f.lat); body.lon = Number(f.lon); }
    if (f.date_start) body.date_start = f.date_start;
    if (f.date_end) body.date_end = f.date_end;
    onSubmit(body);
  };
  return (
    <form className="panel grid gap-3 md:grid-cols-3" onSubmit={submit}>
      <Field label={t("entity_type")}><select className="field" value={f.type} onChange={set("type")}>{ENTITY_TYPES.map((x) => <option key={x} value={x}>{t(`type_${x}`)}</option>)}</select></Field>
      <div className="md:col-span-2"><Field label={t("name")}><input className="field" required value={f.name} onChange={set("name")} autoFocus /></Field></div>
      <div className="md:col-span-3"><Field label={t("aliases")} help={t("comma_separated")}><input className="field" value={f.aliases} onChange={set("aliases")} /></Field></div>
      <div className="md:col-span-3"><Field label={t("description")}><textarea className="field" rows={2} value={f.description} onChange={set("description")} /></Field></div>
      <Field label={t("lat")}><input className="field" type="number" step="any" min="-90" max="90" value={f.lat} onChange={set("lat")} /></Field>
      <Field label={t("lon")}><input className="field" type="number" step="any" min="-180" max="180" value={f.lon} onChange={set("lon")} /></Field>
      <div />
      {(f.type === "event" || f.date_start) && (
        <>
          <Field label={t("date_start")}><input className="field" value={f.date_start} onChange={set("date_start")} placeholder="YYYY-MM-DD" /></Field>
          <Field label={t("date_end")}><input className="field" value={f.date_end} onChange={set("date_end")} placeholder="YYYY-MM-DD" /></Field>
        </>
      )}
      {f.type === "person" && (
        <label className="flex items-center gap-2 text-[13px] md:col-span-3">
          <input type="checkbox" checked={f.public_figure} onChange={set("public_figure")} />
          <span>{t("public_figure")} <span className="help">— {t("public_figure_help")}</span></span>
        </label>
      )}
      <div className="flex gap-2 md:col-span-3"><button className="btn btn-primary" type="submit">{submitLabel}</button><button className="btn" type="button" onClick={onCancel}>{t("cancel")}</button></div>
    </form>
  );
}

function EnrichPanel({ entity, onDone }) {
  const { t, notify } = useApp();
  const { caseId } = useCase();
  const [qid, setQid] = useState(entity.wikidata_qid || "");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState("");
  const run = async (enricher, extra = {}) => {
    setBusy(enricher);
    try {
      const res = await api.enrich(caseId, { enricher, entity_id: entity.id, ...extra });
      setResult({ enricher, ...res });
      onDone();
    } catch (e) {
      setResult({ enricher, error: e.message, refused: e.status === 403 });
    } finally {
      setBusy("");
    }
  };
  return (
    <Section title={t("enrichers")}>
      {entity.private_person && <p className="chip chip-amber chip-wrap mb-2" style={{ whiteSpace: "normal" }}>{t("private_no_enrich")}</p>}
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Wikidata QID"><input className="field" style={{ width: 120 }} value={qid} onChange={(e) => setQid(e.target.value)} placeholder="Q90" /></Field>
        <button className="btn btn-sm" disabled={!!busy} type="button" onClick={() => run("wikidata", { qid: qid || undefined, dry_run: true })}>{t("preview")}</button>
        <button className="btn btn-sm btn-primary" disabled={!!busy} type="button" onClick={() => run("wikidata", { qid: qid || undefined })}>{busy === "wikidata" ? t("working") : "Wikidata"}</button>
        <button className="btn btn-sm btn-primary" disabled={!!busy} type="button" onClick={() => run("geocode")}>{busy === "geocode" ? t("working") : t("geocode")}</button>
        <button className="btn btn-sm" disabled={!!busy} type="button" onClick={() => run("family_search")}>{t("family_search")}</button>
      </div>
      {result && (
        <div className="mt-3 rounded border p-2 text-[12px]" style={{ borderColor: result.refused ? "#e0a43a88" : "var(--line)" }}>
          {result.error ? <div className={result.refused ? "chip chip-amber chip-wrap" : "chip chip-danger chip-wrap"} style={{ whiteSpace: "normal" }}>{result.error}</div> : (
            <>
              <div><b>{result.enricher}</b> · {result.status}{result.run_id ? ` · run #${result.run_id}` : ""}</div>
              {result.candidates?.length > 0 && (
                <ul className="mt-1">{result.candidates.map((c) => <li key={c.qid}><button className="btn-link" type="button" onClick={() => setQid(c.qid)}>{c.qid}</button> {c.label} <span className="help">— {c.description}</span></li>)}</ul>
              )}
              {result.planned && <ul className="mt-1 list-disc pl-5">{result.planned.map((p, i) => <li key={i}>{p.text}</li>)}</ul>}
              {result.hint && <div className="help">{result.hint}</div>}
              {result.note && <div className="help">{result.note}</div>}
              {result.reason && <div className="help">{result.reason}</div>}
              {result.lat !== undefined && result.display_name && <div>{result.display_name} ({result.lat}, {result.lon}) · {result.precision}</div>}
              {result.apps && Object.entries(result.apps).map(([app, r]) => <div key={app}>{app}: {r.status}{r.error ? ` (${r.error})` : ""}{r.sources_added ? ` +${r.sources_added.length}` : ""}</div>)}
            </>
          )}
        </div>
      )}
    </Section>
  );
}

function EntityDrawer({ id, onClose, onChanged }) {
  const { t, notify } = useApp();
  const { caseId } = useCase();
  const detail = useAsync(() => api.entity(id), [id]);
  const sources = useAsync(() => api.sources(caseId, { include_retracted: false }), [caseId]);
  const [editing, setEditing] = useState(false);
  const [attr, setAttr] = useState({ key: "", value: "", source_id: "", quote: "" });
  const e = detail.data;
  const changed = () => { detail.reload(); onChanged(); };
  const guard = async (fn, okMsg) => {
    try { await fn(); if (okMsg) notify(okMsg); changed(); } catch (err) { notify(err.message); }
  };
  if (!e) return <Drawer title="…" onClose={onClose}>{detail.error ? detail.error.message : t("loading")}</Drawer>;
  return (
    <Drawer title={e.name} onClose={onClose}>
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="chip"><TypeDot type={e.type} /> {t(`type_${e.type}`)}</span>
          {e.private_person && <PrivateChip t={t} />}
          {e.public_figure && <span className="chip chip-accent">{t("public_figure")}</span>}
          {e.wikidata_qid && <a className="chip chip-accent" href={`https://www.wikidata.org/wiki/${e.wikidata_qid}`} target="_blank" rel="noreferrer">{e.wikidata_qid}</a>}
          <span className="mono help">{e.ref}</span>
        </div>
        {e.aliases.length > 0 && <div className="text-[13px]"><span className="help">{t("aliases")}:</span> {e.aliases.join(" · ")}</div>}
        {e.description && <p className="text-[13px]">{e.description}</p>}
        {(e.lat !== null || e.date_start) && (
          <div className="text-[13px]">
            {e.lat !== null && <span className="mr-3">📍 {e.lat.toFixed(4)}, {e.lon.toFixed(4)} <span className="help">({e.geo_precision || "?"})</span></span>}
            {e.date_start && <span>{e.date_start}{e.date_end ? ` → ${e.date_end}` : ""}</span>}
          </div>
        )}
        <div className="flex gap-2">
          <button className="btn btn-sm" type="button" onClick={() => setEditing((v) => !v)}>{t("edit")}</button>
          {e.relations.length === 0 && <ConfirmButton t={t} onConfirm={() => guard(async () => { await api.entityDelete(id); onClose(); }, t("deleted"))} />}
        </div>
        {editing && (
          <EntityForm submitLabel={t("save")} onCancel={() => setEditing(false)}
            initial={{ type: e.type, name: e.name, aliases: e.aliases.join(", "), description: e.description, lat: e.lat ?? "", lon: e.lon ?? "", date_start: e.date_start || "", date_end: e.date_end || "", public_figure: e.public_figure }}
            onSubmit={(body) => guard(async () => { await api.entityUpdate(id, body); setEditing(false); }, t("saved"))} />
        )}
        <Section title={t("attributes")}>
          {Object.keys(e.attributes).length === 0 && <p className="help">{t("no_attributes")}</p>}
          <table className="grid"><tbody>
            {Object.entries(e.attributes).map(([k, a]) => (
              <tr key={k}>
                <td className="help">{k}</td>
                <td>{String(a.value)} {a.source_ids.map((s) => <span key={s} className={a.active_source_ids.includes(s) ? "chip chip-accent ml-1" : "chip chip-danger ml-1"}>[S{s}]</span>)}
                  {a.flag === "unsupported" && <span className="chip chip-danger ml-1">{t("status_unsupported")}</span>}
                  {a.flag === "unsourced" && <span className="chip ml-1">{t("unsourced")}</span>}</td>
                <td><button className="btn btn-sm" type="button" aria-label={t("delete")} onClick={() => guard(() => api.entityUpdate(id, { remove_attributes: [k] }))}>✕</button></td>
              </tr>
            ))}
          </tbody></table>
          <form className="mt-2 grid gap-2 md:grid-cols-4" onSubmit={(ev) => {
            ev.preventDefault();
            const value = { value: attr.value };
            if (attr.source_id) { value.source_id = Number(attr.source_id); value.quote = attr.quote; }
            guard(async () => { await api.entityUpdate(id, { attributes: { [attr.key]: value } }); setAttr({ key: "", value: "", source_id: "", quote: "" }); });
          }}>
            <input className="field" required placeholder={t("attr_name")} value={attr.key} onChange={(ev) => setAttr({ ...attr, key: ev.target.value })} />
            <input className="field" required placeholder={t("attr_value")} value={attr.value} onChange={(ev) => setAttr({ ...attr, value: ev.target.value })} />
            <select className="field" value={attr.source_id} onChange={(ev) => setAttr({ ...attr, source_id: ev.target.value })} aria-label={t("source_word")}>
              <option value="">{t("no_source")}</option>{(sources.data?.items || []).map((s) => <option key={s.id} value={s.id}>{s.cite} {s.title.slice(0, 30)}</option>)}
            </select>
            <button className="btn" type="submit">{t("add")}</button>
            {attr.source_id && <div className="md:col-span-4"><input className="field" placeholder={t("quote")} value={attr.quote} onChange={(ev) => setAttr({ ...attr, quote: ev.target.value })} /></div>}
          </form>
        </Section>
        <Section title={`${t("relations_word")} (${e.relations.length})`}>
          <ul className="space-y-1.5 text-[13px]">
            {e.relations.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-2">
                <StatusChip status={r.status} t={t} />
                <span>{r.direction === "out" ? "→" : "←"} {r.label}</span>
                <span className="help">{r.valid_from || r.valid_to ? `${r.valid_from || "?"}–${r.valid_to || "…"}` : ""}</span>
                <span className="mono help">{r.cite}</span>
              </li>
            ))}
          </ul>
        </Section>
        <EnrichPanel entity={e} onDone={changed} />
      </div>
    </Drawer>
  );
}

function Duplicates({ onMerged }) {
  const { t, notify } = useApp();
  const { caseId } = useCase();
  const dups = useAsync(() => api.duplicates(caseId), [caseId]);
  const [preview, setPreview] = useState(null);
  const items = dups.data?.suggestions || [];
  const doPreview = async (a, b) => {
    try { setPreview({ keep: a, merge: b, plan: await api.entityMerge({ keep_id: a.id, merge_id: b.id, confirm: false }) }); } catch (e) { notify(e.message); }
  };
  const doMerge = async () => {
    try {
      await api.entityMerge({ keep_id: preview.keep.id, merge_id: preview.merge.id, confirm: true });
      notify(t("merged"));
      setPreview(null);
      dups.reload();
      onMerged();
    } catch (e) { notify(e.message); }
  };
  return (
    <Section title={t("duplicates")} right={<span className="chip">{items.length}</span>}>
      <p className="help mb-2">{t("duplicates_help")}</p>
      {items.length === 0 && <p className="help">{t("no_duplicates")}</p>}
      <ul className="space-y-2">
        {items.map((s, i) => (
          <li key={i} className="rounded border p-2 text-[13px]" style={{ borderColor: "var(--line)" }}>
            <div className="flex flex-wrap items-center gap-2"><b>{s.a.name}</b> <span className="help">#{s.a.id}</span> ≟ <b>{s.b.name}</b> <span className="help">#{s.b.id}</span> <span className="chip">{t(`type_${s.a.type}`)}</span><span className="chip chip-accent">{s.score}</span></div>
            <ul className="help ml-4 list-disc">{s.reasons.map((r, n) => <li key={n}>{t(`reason_${r.kind}`)}: {r.detail}</li>)}</ul>
            <div className="mt-1 flex gap-2"><button className="btn btn-sm" type="button" onClick={() => doPreview(s.a, s.b)}>{t("merge_b_into_a")}</button><button className="btn btn-sm" type="button" onClick={() => doPreview(s.b, s.a)}>{t("merge_a_into_b")}</button></div>
          </li>
        ))}
      </ul>
      {preview && (
        <div className="mt-3 rounded border p-3 text-[13px]" style={{ borderColor: "var(--warn)" }}>
          <div>{t("merge_preview", { merge: preview.merge.name, keep: preview.keep.name })}</div>
          <div className="help">{t("merge_moves", { n: preview.plan.relations_moved })}{preview.plan.attribute_conflicts.length > 0 && ` · ${t("attribute_conflicts")}: ${preview.plan.attribute_conflicts.join(", ")}`}</div>
          <div className="mt-2 flex gap-2"><button className="btn btn-sm btn-danger" type="button" onClick={doMerge}>{t("merge_confirm")}</button><button className="btn btn-sm" type="button" onClick={() => setPreview(null)}>{t("cancel")}</button></div>
        </div>
      )}
    </Section>
  );
}

export default function Entities() {
  const { t, notify } = useApp();
  const { caseId, reload, query } = useCase();
  const [type, setType] = useState("");
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState(false);
  const [selected, setSelected] = useState(query?.get("open") ? Number(query.get("open")) : null);
  const list = useAsync(() => api.entities(caseId, { type, q }), [caseId, type, q]);
  const items = list.data?.items || [];
  const changed = () => { list.reload(); reload(); };
  const create = async (body) => {
    try {
      const res = await api.entityAdd(caseId, body);
      notify(res.created ? t("entity_created", { name: res.entity.name }) : t("entity_updated", { name: res.entity.name }));
      if (res.possible_duplicates?.length) notify(`${t("possible_duplicates")}: ${res.possible_duplicates.map((d) => d.name).join(", ")}`);
      setAdding(false);
      changed();
    } catch (e) { notify(e.message); }
  };
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <input className="field" style={{ width: 240 }} placeholder={t("search")} value={q} onChange={(e) => setQ(e.target.value)} aria-label={t("search")} />
        <select className="field" style={{ maxWidth: 180 }} value={type} onChange={(e) => setType(e.target.value)} aria-label={t("entity_type")}>
          <option value="">{t("all_types")}</option>{ENTITY_TYPES.map((x) => <option key={x} value={x}>{t(`type_${x}`)}</option>)}
        </select>
        <button className="btn btn-primary ml-auto" type="button" onClick={() => setAdding((v) => !v)}>{t("entity_new")}</button>
      </div>
      {adding && <EntityForm submitLabel={t("create")} onSubmit={create} onCancel={() => setAdding(false)} />}
      {list.error && <Empty>{list.error.message}</Empty>}
      {!list.loading && items.length === 0 && <Empty>{t("entities_empty")}</Empty>}
      {items.length > 0 && (
        <div className="panel overflow-x-auto p-0">
          <table className="grid">
            <thead><tr><th>{t("name")}</th><th>{t("entity_type")}</th><th>{t("aliases")}</th><th>{t("relations_word")}</th><th>{t("sources_word")}</th><th>📍</th></tr></thead>
            <tbody>
              {items.map((e) => (
                <tr key={e.id} className="row-btn" onClick={() => setSelected(e.id)}>
                  <td><b>{e.name}</b> {e.private_person && <PrivateChip t={t} />}</td>
                  <td><span className="chip"><TypeDot type={e.type} /> {t(`type_${e.type}`)}</span></td>
                  <td className="help">{e.aliases.join(", ")}</td>
                  <td className="num">{e.relation_count}</td>
                  <td className="num">{e.source_count}</td>
                  <td>{e.lat !== null ? "✓" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Duplicates onMerged={changed} />
      {selected && <EntityDrawer id={selected} onClose={() => setSelected(null)} onChanged={changed} />}
    </div>
  );
}
