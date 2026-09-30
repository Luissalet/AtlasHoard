import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { useApp } from "../App.jsx";
import { Empty, Field, Section, useAsync } from "../components/ui.jsx";

export default function Settings() {
  const { t, notify, health } = useApp();
  const data = useAsync(() => api.settings(), []);
  const [sources, setSources] = useState("");
  const [tools, setTools] = useState({});
  const s = data.data;
  useEffect(() => {
    if (s) { setSources(s.family_sources.join(", ")); setTools(s.family_tools || {}); }
  }, [s]);

  const save = async (patch) => {
    try { await api.settingsUpdate(patch); notify(t("saved")); data.reload(); } catch (e) { notify(e.message); }
  };
  if (data.error) return <Empty>{data.error.message}</Empty>;
  if (!s) return <div className="help">{t("loading")}</div>;
  const ids = sources.split(",").map((x) => x.trim()).filter(Boolean);

  return (
    <div className="max-w-3xl space-y-4">
      <h1 className="text-[22px] font-semibold">{t("nav_settings")}</h1>
      <Section title={t("geocoding")}>
        <label className="flex items-start gap-2 text-[13px]">
          <input type="checkbox" checked={s.geocode.setting} disabled={s.geocode.env_disabled} onChange={(e) => save({ geocode_enabled: e.target.checked })} />
          <span>{t("geocode_toggle")}<span className="help block">{t("geocode_help")}</span>
            {s.geocode.env_disabled && <span className="chip chip-amber mt-1">{t("geocode_env_off")}</span>}</span>
        </label>
      </Section>
      <Section title={t("family_search")}>
        <p className="help mb-2">{t("family_search_help")}</p>
        <Field label={t("family_apps")}><input className="field" value={sources} onChange={(e) => setSources(e.target.value)} /></Field>
        <div className="mt-2 grid gap-2 md:grid-cols-2">
          {ids.map((id) => (
            <Field key={id} label={`${id}: ${t("tool_name")}`}><input className="field mono" value={tools[id] || ""} onChange={(e) => setTools({ ...tools, [id]: e.target.value })} /></Field>
          ))}
        </div>
        <button type="button" className="btn btn-primary mt-3" onClick={() => save({ family_sources: ids, family_tools: Object.fromEntries(ids.filter((id) => tools[id]).map((id) => [id, tools[id]])) })}>{t("save")}</button>
      </Section>
      <Section title={t("limits")}>
        <ul className="space-y-1 text-[13px]">
          <li>{t("stale_after", { n: s.stale_days })}</li>
          <li>{s.allow_private_urls ? t("private_urls_on") : t("private_urls_off")}</li>
          <li>{s.file_roots.length ? `${t("file_roots")}: ${s.file_roots.join(", ")}` : t("file_roots_any")}</li>
        </ul>
      </Section>
      <Section title={t("about")}>
        <div className="help">Atlas's Hoard {health?.version || ""}</div>
        <div className="help">{t("credits")}</div>
      </Section>
    </div>
  );
}
