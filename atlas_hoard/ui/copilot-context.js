"use strict";
// Pure helpers that describe the open view to the family assistant panel.
// Loaded as a classic script in the browser and required by node tests.
(function (root) {
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

  // Only the fields the person actually changed; used to send partial saves.
  function changedFields(initial, draft) {
    const base = initial || {};
    return Object.fromEntries(Object.entries(draft || {}).filter(([key, value]) => !same(value, base[key])));
  }

  // Ask every open form for its unsaved fields. Each form answers with
  // detail.provide({form, mode, fields, ...}); answers are keyed by form name.
  function editorContext(target, detail) {
    const found = {};
    target.dispatchEvent(new CustomEvent("atlas:context-request", {
      detail: {
        ...(detail || {}),
        provide: (value) => { if (value && typeof value === "object" && value.form) found[value.form] = value; },
      },
    }));
    return Object.keys(found).length ? found : undefined;
  }

  // One trailing call per burst, so the event and onTurnEnd trigger one refresh.
  function debounced(run, wait, timers) {
    const t = timers || { set: (fn, ms) => setTimeout(fn, ms), clear: (h) => clearTimeout(h) };
    let handle = null;
    return function schedule() {
      if (handle !== null) t.clear(handle);
      handle = t.set(() => { handle = null; run(); }, wait);
    };
  }

  // view: result of atlas_project ({project, files}) or null when nothing real is open.
  function buildContext({ view, area, files, editor } = {}) {
    const out = { active_objects: [], view: { page: "home" } };
    const p = view && view.project;
    if (p && p.id) {
      out.project = { external_project_id: String(p.id), title: p.name };
      out.active_objects.push({
        kind: "project", object_id: p.id, title: p.name, sphere: p.sphere, owner: p.owner,
        goal: p.goal, state: p.state, members: p.members, path: p.path, shared_path: p.shared_path,
      });
      for (const f of (files || []).slice(0, 50)) {
        out.active_objects.push({
          kind: "file", object_id: f.id, title: f.title, relative_path: f.relative_path,
          app: f.app, revision: f.revision, state: f.state, exists: f.exists, path: f.path,
        });
      }
      out.view = { page: "project", object_id: p.id, area: area || "shared" };
    }
    if (editor) out.view.editor = editor;
    return out;
  }

  const api = { changedFields, editorContext, debounced, buildContext };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.atlasCopilotContext = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
