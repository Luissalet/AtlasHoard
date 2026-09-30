import React, { useState } from "react";
import { api } from "../../api.js";
import { go, useApp } from "../../App.jsx";
import { useCase } from "../../components/caseContext.js";
import { ConfirmButton, Empty, Section, StatusChip } from "../../components/ui.jsx";
import { STATUSES, clock } from "../../format.js";

export default function Overview() {
  const { t, notify, lang } = useApp();
  const { caseId, caseData: c, reload } = useCase();
  const [newQ, setNewQ] = useState("");
  const d = c.dashboard;

  const saveQuestions = async (list) => {
    try {
      await api.caseUpdate(caseId, { open_questions: list });
      reload();
    } catch (e) {
      notify(e.message);
    }
  };
  const undo = async (id) => {
    try {
      const r = await api.enrichmentUndo(id);
      notify(t("undone_run", { id, n: r.removed.relations.length + r.removed.entities.length + r.removed.sources.length }));
      reload();
    } catch (e) {
      notify(e.message);
    }
  };
  const tile = (label, value, tab) => (
    <a className="card text-center" href={`#/case/${caseId}/${tab}`}>
      <div className="num text-[26px] font-semibold">{value}</div>
      <div className="help">{label}</div>
    </a>
  );
  const attention = d.unsupported_relations.length + d.disputed_relations.length + d.stale_facts.length + d.contradictions.length
    + d.entities_without_relations.length + d.hypotheses_without_ratings.length;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {tile(t("sources_word"), c.counts.sources, "sources")}
        {tile(t("entities_word"), c.counts.entities, "entities")}
        {tile(t("relations_word"), c.counts.relations, "relations")}
        {tile(t("hypotheses_word"), c.counts.hypotheses, "hypotheses")}
      </div>
      <Section title={t("relations_by_status")}>
        <div className="flex flex-wrap gap-3">
          {STATUSES.map((s) => (
            <a key={s} href={`#/case/${caseId}/relations?status=${s}`} className="flex items-center gap-2 no-underline" style={{ color: "inherit" }}>
              <StatusChip status={s} t={t} /> <span className="num">{c.counts.relations_by_status[s] || 0}</span>
            </a>
          ))}
          {c.counts.sources_retracted > 0 && <span className="chip chip-danger">{c.counts.sources_retracted} {t("sources_retracted")}</span>}
        </div>
      </Section>
      <div className="grid gap-4 lg:grid-cols-2">
        <Section title={t("needs_attention")} right={<span className="chip">{attention}</span>}>
          {attention === 0 && <p className="help">{t("nothing_pending")}</p>}
          <ul className="space-y-1.5 text-[13px]">
            {d.unsupported_relations.map((r) => <li key={`u${r.id}`}><span className="chip chip-danger">{t("status_unsupported")}</span> <a href={`#/case/${caseId}/relations?status=unsupported`}>{r.label}</a></li>)}
            {d.disputed_relations.map((r) => <li key={`d${r.id}`}><span className="chip chip-amber">{t("status_disputed")}</span> {r.label}</li>)}
            {d.contradictions.filter((k) => k.kind === "functional_conflict").map((k, n) => <li key={`c${n}`}><span className="chip chip-amber">{t("conflict")}</span> {k.note}</li>)}
            {d.stale_facts.map((r) => <li key={`s${r.id}`}><span className="chip">{t("stale")}</span> {r.label} <span className="help">({r.reason})</span></li>)}
            {d.entities_without_relations.map((e) => <li key={`o${e.id}`}><span className="chip">{t("no_relations")}</span> {e.name}</li>)}
            {d.hypotheses_without_ratings.map((h) => <li key={`h${h}`}><span className="chip">{t("no_ratings")}</span> H{h}</li>)}
          </ul>
        </Section>
        <Section title={t("open_questions")}>
          <ul className="space-y-1.5 text-[13px]">
            {c.open_questions.map((q, i) => (
              <li key={i} className="flex items-start justify-between gap-2"><span>{q}</span>
                <button type="button" className="btn btn-sm" aria-label={t("delete")} onClick={() => saveQuestions(c.open_questions.filter((_, n) => n !== i))}>✕</button></li>
            ))}
          </ul>
          {c.open_questions.length === 0 && <p className="help">{t("no_open_questions")}</p>}
          <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (newQ.trim()) { saveQuestions([...c.open_questions, newQ.trim()]); setNewQ(""); } }}>
            <input className="field" value={newQ} onChange={(e) => setNewQ(e.target.value)} placeholder={t("add_question")} />
            <button className="btn" type="submit">{t("add")}</button>
          </form>
        </Section>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Section title={t("enrichment_runs")}>
          {c.recent_enrichment_runs.length === 0 && <p className="help">{t("no_runs")}</p>}
          <ul className="space-y-1.5 text-[13px]">
            {c.recent_enrichment_runs.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-2">
                <span className="chip chip-accent">{r.enricher}</span> #{r.id}
                <span className={r.status === "ok" ? "chip chip-ok" : "chip"}>{r.status}</span>
                <span className="help">{clock(r.ts, lang)}</span>
                {r.status === "ok" && <ConfirmButton t={t} label={t("undo")} confirmLabel={t("undo_confirm")} onConfirm={() => undo(r.id)} />}
              </li>
            ))}
          </ul>
        </Section>
        <Section title={t("recent_activity")} right={<a href={`#/case/${caseId}/history`} className="help">{t("tab_history")}</a>}>
          <ul className="space-y-1 text-[13px]">
            {c.recent_history.map((h) => <li key={h.id}><span className="chip">{h.caller}</span> {h.summary} <span className="help">{clock(h.ts, lang)}</span></li>)}
          </ul>
        </Section>
      </div>
      {c.summary && <Section title={t("case_summary")}><p className="whitespace-pre-wrap text-[13px]">{c.summary}</p></Section>}
    </div>
  );
}
