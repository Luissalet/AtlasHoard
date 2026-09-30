import React, { useState } from "react";
import { api } from "../../api.js";
import { useApp } from "../../App.jsx";
import { useCase } from "../../components/caseContext.js";
import { Empty, useAsync } from "../../components/ui.jsx";
import { clock } from "../../format.js";

export default function History() {
  const { t, lang } = useApp();
  const { caseId } = useCase();
  const [action, setAction] = useState("");
  const [items, setItems] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [open, setOpen] = useState(null);
  const data = useAsync(async () => {
    const res = await api.history(caseId, { action, limit: 50 });
    setItems(res.items);
    setCursor(res.next_cursor);
    return res;
  }, [caseId, action]);
  const more = async () => {
    const res = await api.history(caseId, { action, limit: 50, cursor });
    setItems((prev) => [...prev, ...res.items]);
    setCursor(res.next_cursor);
  };
  const prefixes = ["case", "source", "entity", "relation", "evidence", "hypothesis", "ach", "enrichment"];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <button type="button" className={action === "" ? "btn btn-sm btn-active" : "btn btn-sm"} onClick={() => setAction("")}>{t("all")}</button>
        {prefixes.map((p) => <button key={p} type="button" className={action === p ? "btn btn-sm btn-active" : "btn btn-sm"} onClick={() => setAction(p)}>{p}</button>)}
        {data.data && <span className="help ml-auto">{data.data.total} {t("entries")}</span>}
      </div>
      {data.error && <Empty>{data.error.message}</Empty>}
      {data.data && items.length === 0 && <Empty>{t("history_empty")}</Empty>}
      <ul className="space-y-1.5">
        {items.map((h) => (
          <li key={h.id} className="panel py-2 text-[13px]">
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="mono help w-[110px] shrink-0">{clock(h.ts, lang)}</span>
              <span className="chip chip-accent">{h.action}</span>
              <span className="chip">{h.caller}</span>
              <span className="min-w-0 flex-1">{h.summary}</span>
              {(h.before || h.after) && <button type="button" className="btn-link text-[12px]" onClick={() => setOpen(open === h.id ? null : h.id)}>{t("details")}</button>}
            </div>
            {open === h.id && (
              <pre className="mono mt-2 overflow-x-auto rounded p-2" style={{ background: "var(--field)" }}>{JSON.stringify({ before: h.before, after: h.after }, null, 2)}</pre>
            )}
          </li>
        ))}
      </ul>
      {cursor && <button type="button" className="btn" onClick={more}>{t("load_more")}</button>}
    </div>
  );
}
