import React, { useEffect, useState } from "react";
import { STATUS_COLORS, RATING_COLORS } from "../format.js";

export function Icon({ d, size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

export function Empty({ children }) {
  return <div className="panel help text-center">{children}</div>;
}

// One chip per relation status, same colours in the list, the graph and the report.
export function StatusChip({ status, t }) {
  const color = STATUS_COLORS[status] || STATUS_COLORS.claimed;
  return (
    <span className="chip" title={t(`status_help_${status}`)}>
      <span className="dot" style={{ background: color }} />
      {t(`status_${status}`)}
    </span>
  );
}

export function GradeChip({ source }) {
  const low = source.reliability === "F" || source.credibility === "6";
  return (
    <span className={low ? "chip" : "chip chip-accent"} title={`${source.reliability} / ${source.credibility}`}>
      {source.grade || `${source.reliability}${source.credibility}`}
    </span>
  );
}

export function RatingCell({ rating, inactive }) {
  if (!rating) return <span className="help">·</span>;
  return (
    <span className="chip" style={{ background: `${RATING_COLORS[rating]}33`, color: RATING_COLORS[rating], opacity: inactive ? 0.45 : 1, textDecoration: inactive ? "line-through" : "none" }}>
      {rating}
    </span>
  );
}

export function PrivateChip({ t }) {
  return <span className="chip chip-amber" title={t("private_help")}>{t("private_person")}</span>;
}

export function CopyButton({ value, t }) {
  const [copied, setCopied] = useState(false);
  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      // clipboard may be unavailable
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button type="button" className="btn btn-sm" onClick={onCopy}>
      {copied ? t("copied") : t("copy")}
    </button>
  );
}

export function ConfirmButton({ label, confirmLabel, onConfirm, t, className = "btn btn-sm btn-danger" }) {
  const [pending, setPending] = useState(false);
  if (pending) {
    return (
      <span className="inline-flex gap-1">
        <button type="button" className={className} onClick={() => { setPending(false); onConfirm(); }}>{confirmLabel || t("confirm")}</button>
        <button type="button" className="btn btn-sm" onClick={() => setPending(false)}>{t("cancel")}</button>
      </span>
    );
  }
  return <button type="button" className={className} onClick={() => setPending(true)}>{label || t("delete")}</button>;
}

export function Tabs({ tabs, active, onChange }) {
  return (
    <div role="tablist" className="tabs">
      {tabs.map((tab) => (
        <button key={tab.key} type="button" role="tab" className="tab" aria-selected={tab.key === active} onClick={() => onChange(tab.key)}>
          {tab.label}
          {tab.badge !== undefined && tab.badge !== null && <span className="chip">{tab.badge}</span>}
        </button>
      ))}
    </div>
  );
}

export function Drawer({ title, onClose, children }) {
  useEffect(() => {
    const onKey = (event) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label={title}>
        <div className="mb-3 flex items-start justify-between gap-3">
          <h2 className="text-[17px] font-semibold">{title}</h2>
          <button type="button" className="btn btn-sm" onClick={onClose}>✕</button>
        </div>
        {children}
      </aside>
    </>
  );
}

export function Field({ label, children, help }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {help && <span className="help">{help}</span>}
    </label>
  );
}

export function Section({ title, right, children }) {
  return (
    <section className="panel">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h3 className="text-[14px] font-semibold">{title}</h3>
        {right}
      </div>
      {children}
    </section>
  );
}

// Minimal Markdown renderer for the report: headings, lists, quotes, tables, bold/italic/code. No raw HTML is ever injected.
function inline(text, keyBase) {
  const parts = [];
  const re = /(\*\*[^*]+\*\*|_[^_]+_|`[^`]+`)/g;
  let last = 0;
  let m;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const token = m[0];
    if (token.startsWith("**")) parts.push(<strong key={`${keyBase}-${i++}`}>{token.slice(2, -2)}</strong>);
    else if (token.startsWith("`")) parts.push(<code key={`${keyBase}-${i++}`} className="mono">{token.slice(1, -1)}</code>);
    else parts.push(<em key={`${keyBase}-${i++}`}>{token.slice(1, -1)}</em>);
    last = m.index + token.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export function Markdown({ text }) {
  const lines = (text || "").split("\n");
  const out = [];
  let i = 0;
  let key = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^#{1,3} /.test(line)) {
      const level = line.match(/^#+/)[0].length;
      const Tag = `h${level}`;
      out.push(<Tag key={key++}>{inline(line.replace(/^#+ /, ""), key)}</Tag>);
      i++;
    } else if (/^\s*- /.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*- /.test(lines[i])) {
        const item = [inline(lines[i].replace(/^\s*- /, ""), key)];
        i++;
        while (i < lines.length && /^\s+> /.test(lines[i])) {
          item.push(<blockquote key={`q${i}`}>{inline(lines[i].replace(/^\s+> /, ""), i)}</blockquote>);
          i++;
        }
        items.push(<li key={items.length}>{item}</li>);
      }
      out.push(<ul key={key++}>{items}</ul>);
    } else if (/^\|/.test(line)) {
      const rows = [];
      while (i < lines.length && /^\|/.test(lines[i])) {
        if (!/^\|[-| ]+\|$/.test(lines[i])) rows.push(lines[i].split("|").slice(1, -1).map((c) => c.trim()));
        i++;
      }
      out.push(
        <table key={key++}>
          <thead><tr>{rows[0].map((c, n) => <th key={n}>{c}</th>)}</tr></thead>
          <tbody>{rows.slice(1).map((r, n) => <tr key={n}>{r.map((c, m) => <td key={m}>{inline(c, m)}</td>)}</tr>)}</tbody>
        </table>,
      );
    } else if (/^> /.test(line)) {
      out.push(<blockquote key={key++}>{inline(line.slice(2), key)}</blockquote>);
      i++;
    } else if (line.trim() === "") {
      i++;
    } else {
      out.push(<p key={key++}>{inline(line.replace(/\s{2}$/, ""), key)}</p>);
      i++;
    }
  }
  return <div className="md">{out}</div>;
}

export function useAsync(fn, deps) {
  const [state, setState] = useState({ loading: true, data: null, error: null });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true }));
    Promise.resolve()
      .then(fn)
      .then((data) => alive && setState({ loading: false, data, error: null }))
      .catch((error) => alive && setState({ loading: false, data: null, error }));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { ...state, reload: () => setTick((n) => n + 1) };
}
