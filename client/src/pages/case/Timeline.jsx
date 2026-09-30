import React, { useState } from "react";
import { api } from "../../api.js";
import { useApp } from "../../App.jsx";
import { useCase } from "../../components/caseContext.js";
import { Empty, Field, Section, StatusChip, useAsync } from "../../components/ui.jsx";
import { ENTITY_TYPES, TYPE_COLORS } from "../../format.js";

export default function Timeline() {
  const { t } = useApp();
  const { caseId } = useCase();
  const [asOf, setAsOf] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [gap, setGap] = useState(365);
  const [types, setTypes] = useState([]);
  const [entityId, setEntityId] = useState("");
  const ents = useAsync(() => api.entities(caseId, { limit: 200 }), [caseId]);
  const data = useAsync(
    () => api.timeline(caseId, { as_of: asOf, date_from: from, date_to: to, gap_days: gap, types: types.join(","), entity_id: entityId }),
    [caseId, asOf, from, to, gap, types.join(","), entityId],
  );
  const d = data.data;
  const toggle = (type) => setTypes(types.includes(type) ? types.filter((x) => x !== type) : [...types, type]);

  // Interleave the gaps between entries so a hole in the record is as visible as an event.
  const rows = [];
  if (d) {
    d.entries.forEach((entry, n) => {
      const prev = d.entries[n - 1];
      const gapHere = prev && d.gaps.find((g) => g.from === prev.date && g.to === entry.date);
      if (gapHere) rows.push({ gap: gapHere, key: `g${n}` });
      rows.push({ entry, key: `e${n}` });
    });
  }
  const kindLabel = { event: t("tl_event"), relation_start: t("tl_start"), relation_end: t("tl_end") };

  return (
    <div className="space-y-4">
      <div className="panel grid gap-3 md:grid-cols-5">
        <Field label={t("as_of")} help={t("as_of_help")}><input className="field" value={asOf} onChange={(e) => setAsOf(e.target.value)} placeholder="YYYY[-MM[-DD]]" /></Field>
        <Field label={t("date_from")}><input className="field" value={from} onChange={(e) => setFrom(e.target.value)} placeholder="YYYY" /></Field>
        <Field label={t("date_to")}><input className="field" value={to} onChange={(e) => setTo(e.target.value)} placeholder="YYYY" /></Field>
        <Field label={t("gap_days")}><input className="field" type="number" min="1" value={gap} onChange={(e) => setGap(Number(e.target.value) || 365)} /></Field>
        <Field label={t("entity_word")}>
          <select className="field" value={entityId} onChange={(e) => setEntityId(e.target.value)}>
            <option value="">{t("all")}</option>
            {(ents.data?.items || []).map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
          </select>
        </Field>
        <div className="flex flex-wrap gap-1.5 md:col-span-5">
          {ENTITY_TYPES.map((type) => (
            <button key={type} type="button" className={types.includes(type) ? "btn btn-sm btn-active" : "btn btn-sm"} onClick={() => toggle(type)}>{t(`type_${type}`)}</button>
          ))}
        </div>
      </div>
      {data.error && <Empty>{data.error.message}</Empty>}
      {d && d.contradictions.length > 0 && (
        <Section title={t("contradictions")} right={<span className="chip chip-amber">{d.contradictions.length}</span>}>
          <ul className="space-y-1 text-[13px]">{d.contradictions.map((c, n) => <li key={n}><span className="chip chip-amber">{c.kind === "disputed" ? t("status_disputed") : t("conflict")}</span> {c.note}</li>)}</ul>
        </Section>
      )}
      {d && rows.length === 0 && <Empty>{t("timeline_empty")}</Empty>}
      {d && rows.length > 0 && (
        <ol className="space-y-1.5" aria-label={t("tab_timeline")}>
          {rows.map((row) => row.gap ? (
            <li key={row.key} className="help ml-[110px] border-l-2 border-dashed pl-3" style={{ borderColor: "var(--warn)" }}>
              ⋯ {t("gap_of", { days: row.gap.days, from: row.gap.from, to: row.gap.to })}
            </li>
          ) : (
            <li key={row.key} className="panel flex flex-wrap items-baseline gap-3 py-2" style={row.entry.active_at_as_of === false ? { opacity: 0.55 } : undefined}>
              <span className="mono w-[96px] shrink-0">{row.entry.date}</span>
              {row.entry.kind === "event" ? (
                <>
                  <span className="dot" style={{ background: TYPE_COLORS.event }} />
                  <span className="font-semibold">{row.entry.name}</span>
                  {row.entry.date_end && <span className="help">→ {row.entry.date_end}</span>}
                  <span className="chip">{row.entry.source_count} {t("sources_word")}</span>
                </>
              ) : (
                <>
                  <span className="chip">{kindLabel[row.entry.kind]}</span>
                  <span>{row.entry.label}</span>
                  <StatusChip status={row.entry.status} t={t} />
                  {row.entry.stale && <span className="chip chip-amber">{t("stale")}</span>}
                  <span className="mono help">{row.entry.cite}</span>
                </>
              )}
            </li>
          ))}
        </ol>
      )}
      {d?.truncated && <p className="help">{t("truncated", { n: d.total })}</p>}
    </div>
  );
}
