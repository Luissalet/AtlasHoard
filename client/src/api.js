// Thin fetch wrapper: JSON in/out, `{ error }` bodies become exceptions. Every call maps to a REST route
// that runs the same code as the MCP tool of the same name.
async function request(method, path, { params, body } = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params || {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  }
  const response = await fetch(url, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { error: text };
  }
  if (!response.ok) {
    const error = new Error((data && data.error) || `Error ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return data;
}

const e = encodeURIComponent;

export const api = {
  health: () => request("GET", "/api/health"),
  status: () => request("GET", "/api/status"),

  cases: (params) => request("GET", "/api/cases", { params }),
  caseCreate: (body) => request("POST", "/api/cases", { body }),
  caseGet: (id) => request("GET", `/api/cases/${id}`),
  caseUpdate: (id, body) => request("PUT", `/api/cases/${id}`, { body }),
  caseDelete: (id) => request("DELETE", `/api/cases/${id}`, { params: { confirm: "true" } }),

  sources: (id, params) => request("GET", `/api/cases/${id}/sources`, { params }),
  sourcesSearch: (id, q) => request("GET", `/api/cases/${id}/sources/search`, { params: { q } }),
  sourceAdd: (id, body) => request("POST", `/api/cases/${id}/sources`, { body }),
  source: (id, params) => request("GET", `/api/sources/${id}`, { params }),
  sourceUpdate: (id, body) => request("PUT", `/api/sources/${id}`, { body }),
  sourceRetract: (id, body) => request("POST", `/api/sources/${id}/retract`, { body }),
  sourceDelete: (id) => request("DELETE", `/api/sources/${id}`, { params: { confirm: "true" } }),

  entities: (id, params) => request("GET", `/api/cases/${id}/entities`, { params }),
  entityAdd: (id, body) => request("POST", `/api/cases/${id}/entities`, { body }),
  entity: (id, params) => request("GET", `/api/entities/${id}`, { params }),
  entityUpdate: (id, body) => request("PUT", `/api/entities/${id}`, { body }),
  entityDelete: (id) => request("DELETE", `/api/entities/${id}`, { params: { confirm: "true" } }),
  duplicates: (id) => request("GET", `/api/cases/${id}/duplicates`),
  entityMerge: (body) => request("POST", "/api/entities/merge", { body }),

  relations: (id, params) => request("GET", `/api/cases/${id}/relations`, { params }),
  relationAdd: (id, body) => request("POST", `/api/cases/${id}/relations`, { body }),
  relation: (id) => request("GET", `/api/relations/${id}`),
  relationUpdate: (id, body) => request("PUT", `/api/relations/${id}`, { body }),
  relationRetract: (id, body) => request("POST", `/api/relations/${id}/retract`, { body }),
  relationDelete: (id) => request("DELETE", `/api/relations/${id}`, { params: { confirm: "true" } }),
  predicates: () => request("GET", "/api/predicates"),
  predicateSave: (body) => request("PUT", "/api/predicates", { body }),
  predicateDelete: (name) => request("DELETE", `/api/predicates/${e(name)}`),

  timeline: (id, params) => request("GET", `/api/cases/${id}/timeline`, { params }),
  map: (id, params) => request("GET", `/api/cases/${id}/map`, { params }),
  graph: (id, params) => request("GET", `/api/cases/${id}/graph`, { params }),
  evidence: (id) => request("GET", `/api/cases/${id}/evidence`),

  ach: (id, params) => request("GET", `/api/cases/${id}/ach`, { params }),
  hypothesisAdd: (id, body) => request("POST", `/api/cases/${id}/hypotheses`, { body }),
  hypothesisUpdate: (id, body) => request("PUT", `/api/hypotheses/${id}`, { body }),
  hypothesisDelete: (id) => request("DELETE", `/api/hypotheses/${id}`, { params: { confirm: "true" } }),
  achRate: (body) => request("PUT", "/api/ach", { body }),

  enrich: (id, body) => request("POST", `/api/cases/${id}/enrich`, { body }),
  enrichmentRuns: (id) => request("GET", `/api/cases/${id}/enrichment`),
  enrichmentUndo: (runId) => request("POST", `/api/enrichment/${runId}/undo`),

  report: (id, params) => request("GET", `/api/cases/${id}/report`, { params }),
  reportDownloadUrl: (id, lang, useModel) => `/api/cases/${id}/report?format=markdown&raw=true&lang=${lang}&use_model=${useModel}`,
  history: (id, params) => request("GET", `/api/cases/${id}/history`, { params }),

  settings: () => request("GET", "/api/settings"),
  settingsUpdate: (body) => request("PUT", "/api/settings", { body }),
};
