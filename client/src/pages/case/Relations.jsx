import React, { useState } from "react";
import { api } from "../../api.js";
import { useApp } from "../../App.jsx";
import { useCase } from "../../components/caseContext.js";
import { ConfirmButton, Empty, Field, Section, StatusChip, useAsync } from "../../components/ui.jsx";
import { STATUSES, span } from "../../format.js";

function EvidenceFields({ value, onChange, sources, t }) {
  return (
    <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_minmax(0,1fr)]">
      <select className="field" required value={value.source_id} onChange={(e) => onChange({ ...value, source_id: e.target.value })} aria-label={t("source_word")}>
        <option value="">{t("choose_source")}</option>{sources.map((s) => <option key={s.id} value={s.id}>{s.cite} {s.title.slice(0, 40)} ({s.grade})</option>)}
      </select>
      <input className="field" placeholder={t("quote_verbatim")} value={value.quote} onChange={(e) => onChange({ ...value, quote: e.target.value })} />
      <input className="field" placeholder={t("locator")} value={value.locator} onChange={(e) => onChange({ ...value, locator: e.target.value })} />
    </div>
  );
}

function AddRelation({ entities, sources, predicates, onDone }) {
  const { t, notify } = useApp();
  const { caseId } = useCase();
  const [f, setF] = useState({ subject: "", predicate: "", object: "", valid_from: "", valid_to: "", confidence: "0.5", notes: "" });
  const [ev, setEv] = useState({ source_id: "", quote: "", locator: "" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async (event) => {
    event.preventDefault();
    if (!ev.quote.trim() && !ev.locator.trim()) { notify(t("evidence_needs_quote")); return; }
    try {
      const body = { subject: f.subject, predicate: f.predicate, object: f.object, confidence: Number(f.confidence), notes: f.notes,
        evidence: [{ source_id: Number(ev.source_id), quote: ev.quote, locator: ev.locator }] };
      if (f.valid_from) body.valid_from = f.valid_from;
      if (f.valid_to) body.valid_to = f.valid_to;
      const res = await api.relationAdd(caseId, body);
      notify(res.merged_into_existing ? t("evidence_added_existing", { id: res.relation.id }) : t("relation_created", { id: res.relation.id }));
      (res.warnings || []).forEach(notify);
      onDone();
    } catch (e) { notify(e.message); }
  };
  return (
    <form className="panel space-y-3" onSubmit={submit}>
      <datalist id="entity-names">{entities.map((e) => <option key={e.id} value={e.name} />)}</datalist>
      <datalist id="predicate-names">{predicates.map((p) => <option key={p.name} value={p.name}>{p.label}</option>)}</datalist>
      <div className="grid gap-3 md:grid-cols-3">
        <Field label={t("subject")}><input className="field" required list="entity-names" value={f.subject} onChange={set("subject")} /></Field>
        <Field label={t("predicate")}><input className="field" required list="predicate-names" value={f.predicate} onChange={set("predicate")} placeholder="works_for" /></Field>
        <Field label={t("object")}><input className="field" required list="entity-names" value={f.object} onChange={set("object")} /></Field>
        <Field label={t("valid_from")}><input className="field" value={f.valid_from} onChange={set("valid_from")} placeholder="YYYY[-MM[-DD]]" /></Field>
        <Field label={t("valid_to")}><input className="field" value={f.valid_to} onChange={set("valid_to")} placeholder="YYYY[-MM[-DD]]" /></Field>
        <Field label={`${t("confidence")} (${f.confidence})`}><input type="range" min="0" max="1" step="0.05" value={f.confidence} onChange={set("confidence")} className="w-full" /></Field>
      </div>
      <div><span className="label">{t("evidence_required")}</span><EvidenceFields value={ev} onChange={setEv} sources={sources} t={t} /></div>
      <div className="flex gap-2"><button className="btn btn-primary" type="submit">{t("add_relation")}</button><button className="btn" type="button" onClick={onDone}>{t("cancel")}</button></div>
    </form>
  );
}

function RelationRow({ r, sources, open, onToggle, onChanged }) {
  const { t, notify } = useApp();
  const [ev, setEv] = useState({ source_id: "", quote: "", locator: "" });
  const [reason, setReason] = useState("");
  const detail = useAsync(() => (open ? api.relation(r.id) : Promise.resolve(null)), [open, r.id, r.status, r.evidence_total]);
  const run = async (fn, msg) => { try { await fn(); if (msg) notify(msg); onChanged(); } catch (e) { notify(e.message); } };
  const rel = detail.data;
  return (
    <>
      <tr className="row-btn" onClick={onToggle} style={{ opacity: r.status === "retracted" ? 0.6 : 1 }}>
        <td className="num help">{r.id}</td>
        <td style={{ textDecoration: r.status === "retracted" ? "line-through" : "none" }}>
          <b>{r.subject_name}</b> <span style={{ color: "var(--accent)" }}>{r.predicate_label}</span> <b>{r.object_name}</b>
          {(r.subject_private || r.object_private) && <span className="chip chip-amber ml-2">{t("private_person")}</span>}
          {r.flags.map((f) => <span key={f} className="chip chip-danger ml-1" title={f}>{t("derived_flag")}</span>)}
          {r.stale && <span className="chip ml-1" title={r.stale_reason}>{t("stale")}</span>}
          {!r.in_vocabulary && <span className="chip ml-1" title={t("free_predicate")}>{t("free_text")}</span>}
        </td>
        <td><StatusChip status={r.status} t={t} /></td>
        <td className="num">{r.confidence.toFixed(2)}</td>
        <td className="help">{span(r.valid_from, r.valid_to)}</td>
        <td><span className="chip chip-accent" title={t("independent_sources", { n: r.independent_sources })}>{r.evidence_count} {t("evidence_short")}</span></td>
      </tr>
      {open && (
        <tr><td colSpan={6} style={{ background: "#0e1c14" }}>
          <div className="space-y-3 p-2">
            {r.manual_reason && <div className="help">{t("reason")}: {r.manual_reason}</div>}
            {r.stale && <div className="help">⚑ {r.stale_reason}</div>}
            <div>
              <span className="label">{t("evidence_word")} ({r.independent_sources} {t("independent_word")})</span>
              {(rel?.evidence || []).map((e) => (
                <div key={e.id} className="quote" style={{ opacity: e.source_retracted ? 0.5 : 1 }}>
                  {e.quote ? <>“{e.quote}”</> : <span className="help">{t("locator")}: {e.locator}</span>}
                  <div className="help">
                    <span className="mono">{e.cite}</span> {e.source_title} · {e.grade}{e.locator && e.quote ? ` · ${e.locator}` : ""}
                    {e.source_retracted && <span className="chip chip-danger ml-2">{t("retracted")}</span>}
                    {e.quote_in_source === false && <span className="chip chip-amber ml-2" title={t("quote_not_found_help")}>{t("quote_not_found")}</span>}
                    {e.quote_in_source === true && <span className="chip chip-ok ml-2">{t("quote_verified")}</span>}
                    {rel.evidence.length > 1 && <button className="btn-link ml-3" type="button" onClick={() => run(() => api.relationUpdate(r.id, { remove_evidence: [e.id] }), t("saved"))}>{t("remove")}</button>}
                  </div>
                </div>
              ))}
            </div>
            <form className="space-y-2" onSubmit={(e) => {
              e.preventDefault();
              if (!ev.quote.trim() && !ev.locator.trim()) { notify(t("evidence_needs_quote")); return; }
              run(async () => { await api.relationUpdate(r.id, { add_evidence: [{ source_id: Number(ev.source_id), quote: ev.quote, locator: ev.locator }] }); setEv({ source_id: "", quote: "", locator: "" }); }, t("saved"));
            }}>
              <EvidenceFields value={ev} onChange={setEv} sources={sources} t={t} />
              <button className="btn btn-sm" type="submit">{t("add_evidence")}</button>
            </form>
            <div className="flex flex-wrap items-center gap-2">
              {r.status !== "retracted" && (
                <>
                  {r.manual_status === "disputed" ? <button className="btn btn-sm" type="button" onClick={() => run(() => api.relationUpdate(r.id, { status: "clear" }))}>{t("clear_dispute")}</button>
                    : <button className="btn btn-sm" type="button" onClick={() => run(() => api.relationUpdate(r.id, { status: "disputed", reason }), t("saved"))}>{t("mark_disputed")}</button>}
                  {r.manual_status === "confirmed" ? <button className="btn btn-sm" type="button" onClick={() => run(() => api.relationUpdate(r.id, { status: "clear" }))}>{t("unconfirm")}</button>
                    : <button className="btn btn-sm" type="button" disabled={r.independent_sources < 2} title={r.independent_sources < 2 ? t("confirm_needs_two") : ""} onClick={() => run(() => api.relationUpdate(r.id, { status: "confirmed", reason }), t("saved"))}>{t("mark_confirmed")}</button>}
                  <input className="field" style={{ maxWidth: 260 }} placeholder={t("reason")} value={reason} onChange={(e) => setReason(e.target.value)} />
                  <ConfirmButton t={t} label={t("retract")} confirmLabel={t("retract_confirm")} onConfirm={() => run(() => api.relationRetract(r.id, { reason: reason || t("retracted_by_user") }), t("saved"))} />
                </>
              )}
              {r.status === "retracted" && <button className="btn btn-sm" type="button" onClick={() => run(() => api.relationRetract(r.id, { action: "restore" }), t("restored"))}>{t("restore")}</button>}
              <ConfirmButton t={t} onConfirm={() => run(() => api.relationDelete(r.id), t("deleted"))} />
            </div>
          </div>
        </td></tr>
      )}
    </>
  );
}

export default function Relations() {
  const { t } = useApp();
  const { caseId, reload, query } = useCase();
  const [status, setStatus] = useState(query?.get("status") || "");
  const [text, setText] = useState("");
  const [predicate, setPredicate] = useState("");
  const [asOf, setAsOf] = useState("");
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState(null);
  const list = useAsync(() => api.relations(caseId, { status, predicate, as_of: asOf }), [caseId, status, predicate, asOf]);
  const entities = useAsync(() => api.entities(caseId, {}), [caseId]);
  const sources = useAsync(() => api.sources(caseId, { include_retracted: false }), [caseId]);
  const predicates = useAsync(() => api.predicates(), []);
  const all = list.data?.items || [];
  const items = text ? all.filter((r) => r.label.toLowerCase().includes(text.toLowerCase())) : all;
  const changed = () => { list.reload(); reload(); };
  const noSources = (sources.data?.items || []).length === 0;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <input className="field" style={{ width: 220 }} placeholder={t("filter_text")} value={text} onChange={(e) => setText(e.target.value)} aria-label={t("filter_text")} />
        <select className="field" style={{ maxWidth: 170 }} value={status} onChange={(e) => setStatus(e.target.value)} aria-label={t("status")}>
          <option value="">{t("all_statuses")}</option>{STATUSES.map((s) => <option key={s} value={s}>{t(`status_${s}`)}</option>)}
        </select>
        <select className="field" style={{ maxWidth: 190 }} value={predicate} onChange={(e) => setPredicate(e.target.value)} aria-label={t("predicate")}>
          <option value="">{t("all_predicates")}</option>{(predicates.data?.items || []).map((p) => <option key={p.name} value={p.name}>{p.label}</option>)}
        </select>
        <label className="help flex items-center gap-1">{t("as_of")} <input className="field" style={{ width: 120 }} value={asOf} onChange={(e) => setAsOf(e.target.value)} placeholder="YYYY-MM-DD" /></label>
        <button className="btn btn-primary ml-auto" type="button" disabled={noSources || (entities.data?.items || []).length < 2} onClick={() => setAdding((v) => !v)}>{t("add_relation")}</button>
      </div>
      {noSources && <p className="help">{t("relations_need_sources")}</p>}
      {adding && <AddRelation entities={entities.data?.items || []} sources={sources.data?.items || []} predicates={predicates.data?.items || []} onDone={() => { setAdding(false); changed(); }} />}
      {list.error && <Empty>{list.error.message}</Empty>}
      {!list.loading && items.length === 0 && <Empty>{t("relations_empty")}</Empty>}
      {items.length > 0 && (
        <div className="panel overflow-x-auto p-0">
          <table className="grid">
            <thead><tr><th>#</th><th>{t("relation_word")}</th><th>{t("status")}</th><th>{t("confidence")}</th><th>{t("validity")}</th><th>{t("evidence_word")}</th></tr></thead>
            <tbody>{items.map((r) => <RelationRow key={r.id} r={r} sources={sources.data?.items || []} open={open === r.id} onToggle={() => setOpen(open === r.id ? null : r.id)} onChanged={changed} />)}</tbody>
          </table>
        </div>
      )}
      <Section title={t("status_legend")}>
        <ul className="grid gap-1 text-[12px] md:grid-cols-2">{STATUSES.map((s) => <li key={s}><StatusChip status={s} t={t} /> <span className="help">{t(`status_help_${s}`)}</span></li>)}</ul>
      </Section>
    </div>
  );
}
