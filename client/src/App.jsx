import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import { initialLang, makeT, saveLang } from "./i18n.js";
import { Icon } from "./components/ui.jsx";
import Cases from "./pages/Cases.jsx";
import Case from "./pages/Case.jsx";
import Settings from "./pages/Settings.jsx";

const NAV = [
  { path: "cases", key: "nav_cases", icon: "M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" },
  { path: "settings", key: "nav_settings", icon: "M12 15a3 3 0 100-6 3 3 0 000 6zM19 12l2-1-1-3-2 .3-1.4-1.4.3-2-3-1-1 2h-2l-1-2-3 1 .3 2L6.8 7.3 5 7 4 10l2 1v2l-2 1 1 3 2-.3 1.4 1.4-.3 2 3 1 1-2h2l1 2 3-1-.3-2 1.4-1.4 2 .3 1-3-2-1z" },
];

const AppContext = createContext(null);
export const useApp = () => useContext(AppContext);

function useHashRoute() {
  const read = () => {
    const [path, query] = window.location.hash.replace(/^#\/?/, "").split("?");
    const parts = path.split("/");
    return { page: parts[0] || "cases", id: parts[1] || null, tab: parts[2] || null, query: new URLSearchParams(query || "") };
  };
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const onChange = () => setRoute(read());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export const go = (path) => { window.location.hash = `#/${path}`; };

export function Toast({ message, onClose }) {
  useEffect(() => {
    if (!message) return undefined;
    const timer = setTimeout(onClose, 5000);
    return () => clearTimeout(timer);
  }, [message, onClose]);
  if (!message) return null;
  return <div className="toast" role="status" onClick={onClose}>{message}</div>;
}

export default function App() {
  const route = useHashRoute();
  const [lang, setLang] = useState(initialLang);
  const t = useMemo(() => makeT(lang), [lang]);
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);

  useEffect(() => { document.documentElement.lang = lang; }, [lang]);

  const refresh = useCallback(async () => {
    try {
      setHealth(await api.health());
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, []);
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 20000);
    return () => clearInterval(timer);
  }, [refresh]);

  const notify = useCallback((message) => setToast(String(message)), []);
  const value = useMemo(() => ({ health, refresh, notify, t, lang }), [health, refresh, notify, t, lang]);

  const switchLang = () => {
    const next = lang === "es" ? "en" : "es";
    saveLang(next);
    setLang(next);
  };
  const activeNav = route.page === "case" ? "cases" : route.page;

  let body;
  if (route.page === "case" && route.id) body = <Case key={route.id} caseId={Number(route.id)} tab={route.tab} query={route.query} />;
  else if (route.page === "settings") body = <Settings />;
  else body = <Cases />;

  return (
    <AppContext.Provider value={value}>
      <div className="min-h-dvh md:grid md:grid-cols-[208px_minmax(0,1fr)]">
        <aside className="sticky top-0 z-10 border-b md:h-dvh md:self-start md:border-b-0 md:border-r" style={{ background: "var(--sidebar)", borderColor: "var(--line)" }}>
          <div className="flex items-center gap-3 px-4 py-3 md:px-5 md:py-5">
            <img src="/icon-192.png" alt="" width="34" height="34" className="rounded-lg" />
            <div className="text-[15px] font-semibold leading-tight">Atlas's Hoard</div>
          </div>
          <nav aria-label="Sections" className="flex gap-1 overflow-x-auto px-3 pb-2 md:flex-col">
            {NAV.map((p) => (
              <a key={p.path} href={`#/${p.path}`} className="nav-link shrink-0 text-[13px]" aria-current={p.path === activeNav ? "page" : undefined}>
                <Icon d={p.icon} />
                {t(p.key)}
              </a>
            ))}
          </nav>
          <div className="hidden px-5 pt-4 md:block">
            {health && (
              <div className="help text-[11px]">
                {health.counts?.cases ?? 0} {t("nav_cases").toLowerCase()} · {health.counts?.sources ?? 0} {t("sources_word")} · {health.counts?.relations ?? 0} {t("relations_word")}
              </div>
            )}
            <button type="button" className="btn btn-sm mt-4" onClick={switchLang}>{t("language")}</button>
          </div>
        </aside>
        <main className="min-w-0 px-4 py-4 md:px-7 md:py-6">
          {error && (
            <div className="mb-4 rounded-md border p-3 text-[13px]" style={{ background: "var(--danger-bg)", borderColor: "#e5534b66" }} role="alert">
              {t("unreachable")}: {error}. <button type="button" className="btn-link" onClick={refresh}>{t("retry")}</button>
            </div>
          )}
          {body}
          <div className="mt-8 md:hidden">
            <button type="button" className="btn btn-sm" onClick={switchLang}>{t("language")}</button>
          </div>
        </main>
      </div>
      <Toast message={toast} onClose={() => setToast(null)} />
    </AppContext.Provider>
  );
}
