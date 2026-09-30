import React, { useState } from "react";
import { api } from "../../api.js";
import { useApp } from "../../App.jsx";
import { useCase } from "../../components/caseContext.js";
import { CopyButton, Empty, Markdown, Section, useAsync } from "../../components/ui.jsx";
import { download } from "../../format.js";

export default function Report() {
  const { t, lang, notify } = useApp();
  const { caseId } = useCase();
  const [rl, setRl] = useState(lang);
  const [useModel, setUseModel] = useState(true);
  const [run, setRun] = useState(0);
  const data = useAsync(() => api.report(caseId, { format: "markdown", lang: rl, use_model: useModel }), [caseId, rl, useModel, run]);
  const d = data.data;
  const check = d?.citation_check;

  const save = async () => {
    try {
      const res = await fetch(api.reportDownloadUrl(caseId, rl, useModel));
      if (!res.ok) throw new Error(`Error ${res.status}`);
      download(`atlas-case-${caseId}.md`, await res.text());
    } catch (e) { notify(e.message); }
  };

  return (
    <div className="space-y-4">
      <div className="panel flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2"><span className="label mb-0">{t("language")}</span>
          <select className="field" style={{ width: 90 }} value={rl} onChange={(e) => setRl(e.target.value)}><option value="es">es</option><option value="en">en</option></select>
        </label>
        <label className="flex items-center gap-2 text-[13px]"><input type="checkbox" checked={useModel} onChange={(e) => setUseModel(e.target.checked)} /> {t("use_model")}</label>
        <button className="btn btn-sm" type="button" onClick={() => setRun(run + 1)}>{t("regenerate")}</button>
        <span className="ml-auto flex gap-2">
          {d && <CopyButton t={t} value={d.markdown} />}
          <button className="btn btn-primary btn-sm" type="button" onClick={save}>{t("download_md")}</button>
        </span>
      </div>
      {data.error && <Empty>{data.error.message}</Empty>}
      {!d && !data.error && <div className="help">{t("loading")}</div>}
      {d && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
          <div className="panel"><Markdown text={d.markdown} /></div>
          <div className="space-y-3">
            <Section title={t("summary_source")}>
              <span className={d.summary_source === "model" ? "chip chip-accent" : "chip"}>{t(`summary_${d.summary_source}`)}</span>
              {d.model_note && <p className="help mt-1">{d.model_note}</p>}
            </Section>
            <Section title={t("citation_check")} right={<span className={check.ok ? "chip chip-ok" : "chip chip-amber"}>{check.ok ? t("ok") : t("needs_review")}</span>}>
              <p className="help">{t("citation_stats", { cited: check.cited, claims: check.claims })}</p>
              {check.uncited.length > 0 && (
                <div className="mt-2"><div className="label">{t("uncited_sentences")}</div>
                  <ul className="space-y-1 text-[12px]">{check.uncited.map((s, n) => <li key={n} className="quote">{s}</li>)}</ul></div>
              )}
              {check.invalid_citations.length > 0 && <p className="mt-2 text-[12px]"><span className="chip chip-danger">{t("invalid_citations")}</span> {check.invalid_citations.map((i) => `[S${i}]`).join(" ")}</p>}
              {check.retracted_citations.length > 0 && <p className="mt-2 text-[12px]"><span className="chip chip-danger">{t("retracted_citations")}</span> {check.retracted_citations.map((i) => `[S${i}]`).join(" ")}</p>}
            </Section>
          </div>
        </div>
      )}
    </div>
  );
}
