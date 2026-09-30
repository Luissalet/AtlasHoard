import React, { useState } from "react";
import { api } from "../../api.js";
import { useApp } from "../../App.jsx";
import { useCase } from "../../components/caseContext.js";
import { ConfirmButton, Empty, Field, RatingCell, Section, useAsync } from "../../components/ui.jsx";
import { RATINGS, RATING_COLORS } from "../../format.js";

function AddCaseEvidence({ hypotheses, sources, onDone }) {
  const { t, notify } = useApp();
  const [f, setF] = useState({ hypothesis_id: "", source_id: "", quote: "", locator: "", rating: "C" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async (event) => {
    event.preventDefault();
    try {
      await api.achRate({ hypothesis_id: Number(f.hypothesis_id), rating: f.rating, evidence: { source_id: Number(f.source_id), quote: f.quote, locator: f.locator } });
      notify(t("evidence_added"));
      setF({ ...f, quote: "", locator: "" });
      onDone();
    } catch (e) { notify(e.message); }
  };
  return (
    <form className="panel grid gap-3 md:grid-cols-5" onSubmit={submit}>
      <Field label={t("hypothesis_word")}>
        <select className="field" required value={f.hypothesis_id} onChange={set("hypothesis_id")}>
          <option value="">—</option>{hypotheses.map((h) => <option key={h.id} value={h.id}>H{h.id}</option>)}
        </select>
      </Field>
      <Field label={t("source_word")}>
        <select className="field" required value={f.source_id} onChange={set("source_id")}>
          <option value="">{t("choose_source")}</option>{sources.map((s) => <option key={s.id} value={s.id}>{s.cite} {s.title.slice(0, 36)}</option>)}
        </select>
      </Field>
      <Field label={t("quote_verbatim")}><input className="field" value={f.quote} onChange={set("quote")} /></Field>
      <Field label={t("locator")}><input className="field" value={f.locator} onChange={set("locator")} /></Field>
      <Field label={t("rating")}>
        <div className="flex gap-2">
          <select className="field" value={f.rating} onChange={set("rating")}>{RATINGS.map((r) => <option key={r} value={r}>{r}</option>)}</select>
          <button className="btn btn-primary" type="submit">{t("add")}</button>
        </div>
      </Field>
    </form>
  );
}

export default function Hypotheses() {
  const { t, notify } = useApp();
  const { caseId, reload } = useCase();
  const data = useAsync(() => api.ach(caseId, { include_unrated: true }), [caseId]);
  const srcs = useAsync(() => api.sources(caseId, { limit: 200 }), [caseId]);
  const [statement, setStatement] = useState("");
  const [showEv, setShowEv] = useState(false);
  const d = data.data;
  const changed = () => { data.reload(); reload(); };
  const run = async (fn) => { try { await fn(); changed(); } catch (e) { notify(e.message); } };

  if (data.error) return <Empty>{data.error.message}</Empty>;
  if (!d) return <div className="help">{t("loading")}</div>;
  const ratingOf = Object.fromEntries(d.ratings.map((r) => [`${r.hypothesis_id}:${r.evidence_id}`, r]));
  const open = d.hypotheses.filter((h) => h.status === "open");
  const discarded = d.hypotheses.filter((h) => h.status !== "open");

  return (
    <div className="space-y-4">
      <div className="panel" role="note" style={{ borderColor: "var(--accent-strong)" }}>
        <div className="text-[13px]" data-testid="ach-note">{d.note}</div>
        <div className="help mt-1">{d.disclaimer}</div>
      </div>

      <Section title={t("hypotheses_word")} right={<button className="btn btn-sm" type="button" onClick={() => setShowEv(!showEv)}>{t("add_case_evidence")}</button>}>
        <form className="mb-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (statement.trim()) run(async () => { await api.hypothesisAdd(caseId, { statement }); setStatement(""); }); }}>
          <input className="field" value={statement} onChange={(e) => setStatement(e.target.value)} placeholder={t("hypothesis_placeholder")} />
          <button className="btn btn-primary" type="submit">{t("add")}</button>
        </form>
        <ul className="space-y-1.5 text-[13px]">
          {d.hypotheses.map((h) => (
            <li key={h.id} className="flex flex-wrap items-center gap-2" style={h.status !== "open" ? { opacity: 0.6 } : undefined}>
              <span className="chip mono">H{h.id}</span><span className="min-w-0 flex-1">{h.statement}</span>
              {h.least_contradicted && <span className="chip chip-ok">{t("least_contradicted")}</span>}
              {h.score !== null && <span className="chip" title={t("score_help")}>{t("score")} {h.score}</span>}
              <button type="button" className="btn btn-sm" onClick={() => run(() => api.hypothesisUpdate(h.id, { status: h.status === "open" ? "discarded" : "open" }))}>
                {h.status === "open" ? t("discard") : t("reopen")}
              </button>
              <ConfirmButton t={t} onConfirm={() => run(() => api.hypothesisDelete(h.id))} />
            </li>
          ))}
        </ul>
        {d.hypotheses.length === 0 && <p className="help">{t("no_hypotheses")}</p>}
      </Section>

      {showEv && <AddCaseEvidence hypotheses={open} sources={srcs.data?.items || []} onDone={changed} />}

      {open.length > 0 && d.evidence.length > 0 && (
        <Section title={t("ach_matrix")}>
          <div className="mb-2 flex flex-wrap gap-2 text-[12px]">
            {RATINGS.map((r) => <span key={r} className="help"><RatingCell rating={r} /> {t(`rating_${r}`)}</span>)}
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="grid" data-testid="ach-matrix">
              <thead>
                <tr>
                  <th>{t("evidence_word")}</th>
                  {open.map((h) => <th key={h.id} title={h.statement}>H{h.id}</th>)}
                  <th>{t("diagnosticity")}</th>
                </tr>
              </thead>
              <tbody>
                {d.evidence.map((e) => (
                  <tr key={e.id} style={!e.active ? { opacity: 0.55 } : undefined}>
                    <td style={{ minWidth: 240, maxWidth: 420 }}>
                      <span className="mono">E{e.id}</span> <span className="mono help">{e.cite}</span> <span className="chip">{e.grade}</span>
                      {!e.active && <span className="chip chip-danger">{t("source_retracted")}</span>}
                      <div>{e.context}</div>
                      {e.quote && <div className="quote">{e.quote}</div>}
                    </td>
                    {open.map((h) => {
                      const cur = ratingOf[`${h.id}:${e.id}`];
                      return (
                        <td key={h.id}>
                          <select className="field" style={{ width: 70, color: cur ? RATING_COLORS[cur.rating] : undefined, fontWeight: 700 }} aria-label={`H${h.id} E${e.id}`}
                            value={cur?.rating || ""} onChange={(ev) => run(() => api.achRate(ev.target.value ? { hypothesis_id: h.id, evidence_id: e.id, rating: ev.target.value } : { hypothesis_id: h.id, evidence_id: e.id, action: "delete" }))}>
                            <option value="">·</option>{RATINGS.map((r) => <option key={r} value={r}>{r}</option>)}
                          </select>
                        </td>
                      );
                    })}
                    <td className="num">
                      {e.diagnosticity}
                      {e.pivotal && <span className="chip chip-amber ml-1" title={t("pivotal_help")}>{t("pivotal")}</span>}
                      {!e.diagnostic && e.ratings > 0 && <span className="chip ml-1">{t("non_diagnostic")}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td className="help">{t("inconsistency_score")}</td>
                  {open.map((h) => <td key={h.id} className="num" style={{ fontWeight: h.least_contradicted ? 700 : 400, color: h.least_contradicted ? "var(--ok)" : undefined }}>{h.score}</td>)}
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>
        </Section>
      )}
      {open.length > 0 && d.evidence.length === 0 && <Empty>{t("no_evidence_for_ach")}</Empty>}
      {discarded.length > 0 && <p className="help">{discarded.length} {t("discarded_count")}</p>}
    </div>
  );
}
