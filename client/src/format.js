// Small helpers shared by the pages: status colours, dates, ratings.
export const STATUSES = ["claimed", "corroborated", "confirmed", "disputed", "unsupported", "retracted"];
export const STATUS_COLORS = {
  claimed: "var(--st-claimed)",
  corroborated: "var(--st-corroborated)",
  confirmed: "var(--st-confirmed)",
  disputed: "var(--st-disputed)",
  retracted: "var(--st-retracted)",
  unsupported: "var(--st-unsupported)",
};
// Hex twins of the CSS variables for canvas/SVG code that cannot read var().
export const STATUS_HEX = {
  claimed: "#9fb0c3", corroborated: "#5fb3d9", confirmed: "#7fc08a", disputed: "#e0a43a", retracted: "#7d8790", unsupported: "#e5534b",
};
export const TYPE_COLORS = {
  person: "#e8b64a", organization: "#5fb3d9", place: "#7fc08a", event: "#e5534b", document: "#b79cf0", object: "#d98c5f", domain: "#6fd1c4", concept: "#9fb0c3",
};
export const ENTITY_TYPES = ["person", "organization", "place", "event", "document", "object", "domain", "concept"];
export const RATINGS = ["CC", "C", "N", "I", "II", "NA"];
export const RATING_COLORS = { CC: "#3fb27f", C: "#7fc08a", N: "#8aa397", I: "#e0a43a", II: "#e5534b", NA: "#5b7467" };

export function clock(ts, lang) {
  if (!ts) return "—";
  const date = new Date(ts * 1000);
  const locale = lang === "en" ? "en-GB" : "es-ES";
  const sameDay = date.toDateString() === new Date().toDateString();
  const time = date.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
  return sameDay ? time : `${date.toLocaleDateString(locale, { day: "2-digit", month: "short", year: "2-digit" })} ${time}`;
}

export function span(from, to) {
  if (!from && !to) return "";
  return `${from || "?"} – ${to || "…"}`;
}

export function yearOf(date) {
  const m = /^(\d{1,4})/.exec(date || "");
  return m ? Number(m[1]) : null;
}

// "2024" -> "2024-12-31" style upper bound is not needed on the client: the server compares partial dates.
export function asOfFromYear(year) {
  return year === null || year === undefined ? "" : String(year).padStart(4, "0");
}

export function download(filename, text, type = "text/markdown") {
  const url = URL.createObjectURL(new Blob([text], { type: `${type};charset=utf-8` }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
