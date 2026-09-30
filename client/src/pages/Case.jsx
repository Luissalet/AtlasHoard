import React, { useState } from "react";
import { api } from "../api.js";
import { go, useApp } from "../App.jsx";
import { CaseContext } from "../components/caseContext.js";
import { ConfirmButton, CopyButton, Empty, Field, Tabs, useAsync } from "../components/ui.jsx";
import Overview from "./case/Overview.jsx";
import Sources from "./case/Sources.jsx";
import Entities from "./case/Entities.jsx";
import Relations from "./case/Relations.jsx";
import Timeline from "./case/Timeline.jsx";
import MapTab from "./case/MapTab.jsx";
import GraphTab from "./case/GraphTab.jsx";
import Hypotheses from "./case/Hypotheses.jsx";
import Report from "./case/Report.jsx";
import History from "./case/History.jsx";

const TAB_COMPONENTS = {
  overview: Overview, sources: Sources, entities: Entities, relations: Relations, timeline: Timeline,
  map: MapTab, graph: GraphTab, hypotheses: Hypotheses, report: Report, history: History,
};

export default function Case({ caseId, tab, query }) {
  const { t, notify, refresh } = useApp();
  const data = useAsync(() => api.caseGet(caseId), [caseId]);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const active = TAB_COMPONENTS[tab] ? tab : "overview";
  const Body = TAB_COMPONENTS[active];
  const c = data.data;

  if (data.error) return <Empty>{data.error.message} <a href="#/cases">{t("back_to_cases")}</a></Empty>;
  if (!c) return <div className="help">{t("loading")}</div>;

  const tabs = [
    { key: "overview", label: t("tab_overview") },
    { key: "sources", label: t("tab_sources"), badge: c.counts.sources },
    { key: "entities", label: t("tab_entities"), badge: c.counts.entities },
    { key: "relations", label: t("tab_relations"), badge: c.counts.relations },
    { key: "timeline", label: t("tab_timeline") },
    { key: "map", label: t("tab_map") },
    { key: "graph", label: t("tab_graph") },
    { key: "hypotheses", label: t("tab_hypotheses"), badge: c.counts.hypotheses || null },
    { key: "report", label: t("tab_report") },
    { key: "history", label: t("tab_history") },
  ];

  const startEdit = () => {
    setForm({ title: c.title, question: c.question, status: c.status, tags: c.tags.join(", ") });
    setEditing(true);
  };
  const save = async (event) => {
    event.preventDefault();
    try {
      await api.caseUpdate(caseId, { title: form.title, question: form.question, status: form.status, tags: form.tags.split(",").map((s) => s.trim()).filter(Boolean) });
      setEditing(false);
      data.reload();
      refresh();
    } catch (e) {
      notify(e.message);
    }
  };
  const remove = async () => {
    try {
      await api.caseDelete(caseId);
      notify(t("case_deleted"));
      refresh();
      go("cases");
    } catch (e) {
      notify(e.message);
    }
  };

  const ctx = { caseId, caseData: c, reload: data.reload, query };
  return (
    <CaseContext.Provider value={ctx}>
      <div className="space-y-4">
        <div>
          <a href="#/cases" className="help">← {t("nav_cases")}</a>
          {editing ? (
            <form className="panel mt-2 grid gap-3 md:grid-cols-3" onSubmit={save}>
              <Field label={t("case_title")}><input className="field" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
              <Field label={t("case_status")}>
                <select className="field" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                  {["open", "paused", "closed"].map((s) => <option key={s} value={s}>{t(`case_status_${s}`)}</option>)}
                </select>
              </Field>
              <Field label={t("case_tags")}><input className="field" value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} /></Field>
              <div className="md:col-span-3"><Field label={t("case_question")}><textarea className="field" rows={2} value={form.question} onChange={(e) => setForm({ ...form, question: e.target.value })} /></Field></div>
              <div className="flex flex-wrap items-center gap-2 md:col-span-3">
                <button className="btn btn-primary" type="submit">{t("save")}</button>
                <button className="btn" type="button" onClick={() => setEditing(false)}>{t("cancel")}</button>
                <span className="ml-auto"><ConfirmButton t={t} label={t("case_delete")} confirmLabel={t("case_delete_confirm")} onConfirm={remove} /></span>
              </div>
            </form>
          ) : (
            <div className="mt-1 flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <h1 className="text-[22px] font-semibold">{c.title}</h1>
                {c.question && <p className="mt-1 max-w-3xl text-[13px]" style={{ color: "#c9ddd0" }}>{c.question}</p>}
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  <span className={c.status === "open" ? "chip chip-ok" : "chip"}>{t(`case_status_${c.status}`)}</span>
                  {c.tags.map((tag) => <span key={tag} className="chip chip-accent">{tag}</span>)}
                  <span className="mono help">{c.ref}</span>
                </div>
              </div>
              <div className="flex gap-2"><CopyButton t={t} value={c.ref} /><button className="btn btn-sm" type="button" onClick={startEdit}>{t("edit")}</button></div>
            </div>
          )}
        </div>
        <Tabs tabs={tabs} active={active} onChange={(k) => go(`case/${caseId}/${k}`)} />
        <div className="pt-1"><Body /></div>
      </div>
    </CaseContext.Provider>
  );
}
