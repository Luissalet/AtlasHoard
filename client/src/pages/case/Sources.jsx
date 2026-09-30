import React, { useState } from "react";
import { api } from "../../api.js";
import { useApp } from "../../App.jsx";
import { useCase } from "../../components/caseContext.js";
import { ConfirmButton, Empty, Field, GradeChip, Section, useAsync } from "../../components/ui.jsx";
import { clock } from "../../format.js";

const KINDS = ["url", "text", "file", "family_ref", "note"];
const REL = ["A", "B", "C", "D", "E", "F"];
const CRED = ["1", "2", "3", "4", "5", "6"];

function GradeSelects({ value, onChange, t }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      <Field label={t("reliability")} help={t("reliability_help")}>
        <select className="field" value={value.reliability} onChange={(e) => onChange({ ...value, reliability: e.target.value })}>
          {REL.map((r) => <option key={r} value={r}>{r} — {t(`rel_${r}`)}</option>)}
        </select>
      </Field>
      <Field label={t("credibility")} help={t("credibility_help")}>
        <select className="field" value={value.credibility} onChange={(e) => onChange({ ...value, credibility: e.target.value })}>
          {CRED.map((r) => <option key={r} value={r}>{r} — {t(`cred_${r}`)}</option>)}
        </select>
      </Field>
    </div>
  );
}

function AddSource({ onDone }) {
  const { t, notify } = useApp();
  const { caseId } = useCase();
  const [form, setForm] = useState({ kind: "url", title: "", url: "", path: "", text: "", ref: "", revision: "", published_at: "", origin: "", note: "", reliability: "C", credibility: "3" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      const body = { kind: form.kind, title: form.title, reliability: form.reliability, credibility: form.credibility, origin: form.origin, note: form.note, published_at: form.published_at };
      if (form.kind === "url") body.url = form.url;
      if (form.kind === "file") body.path = form.path;
      if (form.kind === "family_ref") { body.ref = form.ref; body.revision = form.revision; body.text = form.text; }
      if (form.kind === "text" || form.kind === "note") { body.text = form.text; body.url = form.url; }
      const res = await api.sourceAdd(caseId, body);
      notify(res.created ? t("source_added", { id: res.source.id }) : t("source_duplicate", { id: res.duplicate_of }));
      onDone();
    } catch (e) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="panel grid gap-3 md:grid-cols-2" onSubmit={submit}>
      <Field label={t("source_kind")}>
        <select className="field" value={form.kind} onChange={set("kind")}>{KINDS.map((k) => <option key={k} value={k}>{t(`kind_${k}`)}</option>)}</select>
      </Field>
      <Field label={t("title")}><input className="field" value={form.title} onChange={set("title")} placeholder={t("title_optional")} /></Field>
      {form.kind === "url" && <div className="md:col-span-2"><Field label="URL" help={t("url_help")}><input className="field" type="url" required value={form.url} onChange={set("url")} placeholder="https://" /></Field></div>}
      {form.kind === "file" && <div className="md:col-span-2"><Field label={t("file_path")} help={t("file_help")}><input className="field" required value={form.path} onChange={set("path")} /></Field></div>}
      {form.kind === "family_ref" && (
        <>
          <Field label="hoard://" help={t("ref_help")}><input className="field" required value={form.ref} onChange={set("ref")} placeholder="hoard://borges/document/12" /></Field>
          <Field label={t("revision")}><input className="field" value={form.revision} onChange={set("revision")} placeholder="sha256:…" /></Field>
          <div className="md:col-span-2"><Field label={t("excerpt")}><textarea className="field" rows={2} value={form.text} onChange={set("text")} /></Field></div>
        </>
      )}
      {(form.kind === "text" || form.kind === "note") && (
        <>
          <div className="md:col-span-2"><Field label={t("text")} help={t("text_help")}><textarea className="field" rows={5} required value={form.text} onChange={set("text")} /></Field></div>
          <div className="md:col-span-2"><Field label={t("reference_url")}><input className="field" value={form.url} onChange={set("url")} placeholder="https://" /></Field></div>
        </>
      )}
      <GradeSelects t={t} value={form} onChange={(v) => setForm({ ...form, ...v })} />
      <Field label={t("published_at")} help="YYYY · YYYY-MM · YYYY-MM-DD"><input className="field" value={form.published_at} onChange={set("published_at")} /></Field>
      <Field label={t("origin")} help={t("origin_help")}><input className="field" value={form.origin} onChange={set("origin")} /></Field>
      <div className="flex gap-2 md:col-span-2"><button className="btn btn-primary" disabled={busy} type="submit">{busy ? t("working") : t("add_source")}</button><button className="btn" type="button" onClick={onDone}>{t("cancel")}</button></div>
    </form>
  );
}

function SourceRow({ source, open, onToggle, onChanged }) {
  const { t, notify, lang } = useApp();
  const detail = useAsync(() => (open ? api.source(source.id, { max_chars: 3000 }) : Promise.resolve(null)), [open, source.id, source.retracted]);
  const [grade, setGrade] = useState({ reliability: source.reliability, credibility: source.credibility, origin: source.origin });
  const [reason, setReason] = useState("");
  const run = async (fn, okMsg) => {
    try {
      const res = await fn();
      if (okMsg) notify(typeof okMsg === "function" ? okMsg(res) : okMsg);
      onChanged();
    } catch (e) {
      notify(e.message);
    }
  };
  return (
    <>
      <tr className="row-btn" onClick={onToggle} style={{ opacity: source.retracted ? 0.6 : 1 }}>
        <td className="mono">{source.cite}</td>
        <td><span style={{ textDecoration: source.retracted ? "line-through" : "none" }}>{source.title}</span>{source.retracted && <span className="chip chip-danger ml-2">{t("retracted")}</span>}</td>
        <td><span className="chip">{t(`kind_${source.kind}`)}</span></td>
        <td><GradeChip source={source} /></td>
        <td className="help">{source.origin}</td>
        <td className="help">{source.published_at || "—"}</td>
        <td className="num">{source.evidence_count}</td>
      </tr>
      {open && (
        <tr><td colSpan={7} style={{ background: "#0e1c14" }}>
          <div className="grid gap-3 p-2 lg:grid-cols-2">
            <div className="space-y-2">
              {source.url && <div className="mono"><a href={source.url.startsWith("file:") ? undefined : source.url} target="_blank" rel="noreferrer">{source.url}</a></div>}
              {source.ref && <div className="mono">{source.ref} <span className="help">{source.ref_revision}</span></div>}
              <div className="help">{t("captured")} {source.captured_at} · hash <span className="mono">{source.content_hash.slice(0, 16)}</span> · {source.text_chars} {t("chars")}</div>
              {source.retracted && <div className="chip chip-danger chip-wrap">{t("retract_reason")}: {source.retract_reason || "—"}</div>}
              <pre className="mono max-h-64 overflow-auto whitespace-pre-wrap rounded border p-2" style={{ borderColor: "var(--line)", background: "var(--field)" }}>{detail.data?.text || (detail.loading ? "…" : t("no_snapshot"))}</pre>
            </div>
            <div className="space-y-3">
              <GradeSelects t={t} value={grade} onChange={(v) => setGrade({ ...grade, ...v })} />
              <Field label={t("origin")} help={t("origin_help")}><input className="field" value={grade.origin} onChange={(e) => setGrade({ ...grade, origin: e.target.value })} /></Field>
              <button className="btn btn-sm" type="button" onClick={() => run(() => api.sourceUpdate(source.id, grade), t("saved"))}>{t("save_grades")}</button>
              <div>
                <span className="label">{t("cited_by")}</span>
                <ul className="space-y-1 text-[12px]">
                  {(detail.data?.evidence || []).map((e) => (
                    <li key={e.id}>{e.relation_id ? `${t("relation_word")} #${e.relation_id}` : e.attribute ? `${t("attribute")} ${e.attribute}` : t("case_evidence")} — <span className="help">{e.quote || e.locator}</span></li>
                  ))}
                  {detail.data && detail.data.evidence.length === 0 && <li className="help">{t("not_cited")}</li>}
                </ul>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {!source.retracted ? (
                  <>
                    <input className="field" style={{ maxWidth: 240 }} placeholder={t("reason")} value={reason} onChange={(e) => setReason(e.target.value)} />
                    <ConfirmButton t={t} label={t("retract")} confirmLabel={t("retract_confirm")}
                      onConfirm={() => run(() => api.sourceRetract(source.id, { action: "retract", reason }), (r) => t("retract_done", { n: r.affected?.relations_unsupported?.length || 0 }))} />
                  </>
                ) : (
                  <button className="btn btn-sm" type="button" onClick={() => run(() => api.sourceRetract(source.id, { action: "restore" }), t("restored"))}>{t("restore")}</button>
                )}
                {source.evidence_count === 0 && <ConfirmButton t={t} onConfirm={() => run(() => api.sourceDelete(source.id), t("deleted"))} />}
              </div>
              <p className="help">{t("retract_help")}</p>
            </div>
          </div>
        </td></tr>
      )}
    </>
  );
}

export default function Sources() {
  const { t } = useApp();
  const { caseId, reload } = useCase();
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState(null);
  const [kind, setKind] = useState("");
  const [showRetracted, setShowRetracted] = useState(true);
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const list = useAsync(() => (query ? api.sourcesSearch(caseId, query) : api.sources(caseId, { kind, include_retracted: showRetracted })), [caseId, kind, showRetracted, query]);
  const items = list.data?.items || [];
  const changed = () => { list.reload(); reload(); };
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); setQuery(q.trim()); }}>
          <input className="field" style={{ width: 260 }} placeholder={t("search_sources")} value={q} onChange={(e) => setQ(e.target.value)} aria-label={t("search_sources")} />
          <button className="btn" type="submit">{t("search")}</button>
          {query && <button className="btn" type="button" onClick={() => { setQ(""); setQuery(""); }}>{t("clear")}</button>}
        </form>
        <select className="field" style={{ maxWidth: 160 }} value={kind} onChange={(e) => setKind(e.target.value)} aria-label={t("source_kind")}>
          <option value="">{t("all_kinds")}</option>{KINDS.map((k) => <option key={k} value={k}>{t(`kind_${k}`)}</option>)}
        </select>
        <label className="help flex items-center gap-1"><input type="checkbox" checked={showRetracted} onChange={(e) => setShowRetracted(e.target.checked)} /> {t("show_retracted")}</label>
        <button className="btn btn-primary ml-auto" type="button" onClick={() => setAdding((v) => !v)}>{t("add_source")}</button>
      </div>
      {adding && <AddSource onDone={() => { setAdding(false); changed(); }} />}
      {list.error && <Empty>{list.error.message}</Empty>}
      {!list.loading && items.length === 0 && <Empty>{query ? t("no_results") : t("sources_empty")}</Empty>}
      {items.length > 0 && (
        <div className="panel overflow-x-auto p-0">
          <table className="grid">
            <thead><tr><th>ID</th><th>{t("title")}</th><th>{t("source_kind")}</th><th>{t("grade")}</th><th>{t("origin")}</th><th>{t("published_at")}</th><th>{t("evidence_word")}</th></tr></thead>
            <tbody>
              {items.map((s) => (
                <React.Fragment key={s.id}>
                  <SourceRow source={s} open={open === s.id} onToggle={() => setOpen(open === s.id ? null : s.id)} onChanged={changed} />
                  {query && s.snippet && <tr><td /><td colSpan={6} className="help">{s.snippet}</td></tr>}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
