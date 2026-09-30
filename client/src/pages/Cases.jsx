import React, { useState } from "react";
import { api } from "../api.js";
import { go, useApp } from "../App.jsx";
import { Empty, Field, useAsync } from "../components/ui.jsx";
import { clock } from "../format.js";

export default function Cases() {
  const { t, notify, lang, refresh } = useApp();
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ title: "", question: "", tags: "" });
  const list = useAsync(() => api.cases({ status, query }), [status, query]);

  const create = async (event) => {
    event.preventDefault();
    try {
      const res = await api.caseCreate({ title: form.title, question: form.question, tags: form.tags.split(",").map((s) => s.trim()).filter(Boolean) });
      notify(t("case_created"));
      refresh();
      go(`case/${res.case.id}/overview`);
    } catch (e) {
      notify(e.message);
    }
  };

  const items = list.data?.items || [];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-[22px] font-semibold">{t("cases_title")}</h1>
        <button type="button" className="btn btn-primary" onClick={() => setCreating((v) => !v)}>{t("case_new")}</button>
      </div>
      <p className="help max-w-3xl">{t("cases_intro")}</p>
      {creating && (
        <form className="panel grid gap-3 md:grid-cols-2" onSubmit={create}>
          <Field label={t("case_title")}><input className="field" required maxLength={200} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} autoFocus /></Field>
          <Field label={t("case_tags")} help={t("comma_separated")}><input className="field" value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} /></Field>
          <div className="md:col-span-2"><Field label={t("case_question")}><textarea className="field" rows={2} value={form.question} onChange={(e) => setForm({ ...form, question: e.target.value })} placeholder={t("case_question_ph")} /></Field></div>
          <div className="flex gap-2 md:col-span-2"><button className="btn btn-primary" type="submit">{t("create")}</button><button className="btn" type="button" onClick={() => setCreating(false)}>{t("cancel")}</button></div>
        </form>
      )}
      <div className="flex flex-wrap gap-2">
        <input className="field" style={{ maxWidth: 320 }} placeholder={t("search")} value={query} onChange={(e) => setQuery(e.target.value)} aria-label={t("search")} />
        <select className="field" style={{ maxWidth: 180 }} value={status} onChange={(e) => setStatus(e.target.value)} aria-label={t("case_status")}>
          <option value="">{t("all_statuses")}</option>
          {["open", "paused", "closed"].map((s) => <option key={s} value={s}>{t(`case_status_${s}`)}</option>)}
        </select>
      </div>
      {list.error && <Empty>{list.error.message}</Empty>}
      {!list.loading && items.length === 0 && <Empty>{t("cases_empty")}</Empty>}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {items.map((c) => (
          <a key={c.id} className="card" href={`#/case/${c.id}/overview`}>
            <div className="flex items-start justify-between gap-2">
              <h2 className="text-[15px] font-semibold">{c.title}</h2>
              <span className={c.status === "open" ? "chip chip-ok" : "chip"}>{t(`case_status_${c.status}`)}</span>
            </div>
            {c.question && <p className="help mt-1 line-clamp-2">{c.question}</p>}
            <div className="mt-3 flex flex-wrap gap-1.5 text-[12px]">
              <span className="chip">{c.counts.sources} {t("sources_word")}</span>
              <span className="chip">{c.counts.entities} {t("entities_word")}</span>
              <span className="chip">{c.counts.relations} {t("relations_word")}</span>
              {c.counts.hypotheses > 0 && <span className="chip">{c.counts.hypotheses} {t("hypotheses_word")}</span>}
              {(c.counts.relations_by_status?.unsupported || 0) > 0 && <span className="chip chip-danger">{c.counts.relations_by_status.unsupported} {t("status_unsupported").toLowerCase()}</span>}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {c.tags.map((tag) => <span key={tag} className="chip chip-accent">{tag}</span>)}
              <span className="help ml-auto">{clock(c.updated_ts, lang)}</span>
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}
