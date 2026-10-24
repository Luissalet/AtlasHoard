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

  const projectFields = project => ({name:project.name, goal:project.goal, members:[...project.members].sort(), state:project.state});
  const inputValue = (key, value, owner) => key === "members" ? value.filter(id => id !== owner).join(", ") : value;
  function projectPatch(draft) {
    const values = {name:draft.values.name.trim(), goal:draft.values.goal.trim(),
      members:[...new Set([draft.owner,...draft.values.members.split(",").map(id=>id.trim().toLowerCase()).filter(Boolean)])].sort(),
      state:draft.values.state};
    const patch = changedFields(draft.baseline, values);
    if (JSON.stringify(patch) !== JSON.stringify(draft.patch)) draft.requestId = null;
    draft.patch = patch;
  }
  function projectDraft(project) {
    const baseline = projectFields(project);
    return {owner:project.owner, baseline, values:Object.fromEntries(Object.entries(baseline).map(([key,value])=>[key,inputValue(key,value,project.owner)])), patch:{}, requestId:null, saving:false};
  }
  function refreshProjectDraft(draft, project) {
    const latest = projectFields(project);
    for (const [key,value] of Object.entries(latest)) {
      if (!(key in draft.patch)) draft.values[key] = inputValue(key,value,project.owner);
    }
    draft.baseline = latest;
    projectPatch(draft);
    return draft;
  }
  function editProjectDraft(draft, key, value) {
    draft.values[key] = value;
    projectPatch(draft);
  }

  function fileDraft() {
    return {values:{relative_path:"",title:""}, open:false, saving:false, requestId:null, receipt:null, error:""};
  }
  function editFileDraft(draft, key, value) {
    draft.values[key] = value;
    draft.requestId = null;
  }
  async function saveFileDraft(draft, send, newRequestId) {
    const values = {...draft.values};
    const requestId = draft.requestId ||= newRequestId();
    draft.saving = true;
    draft.error = "";
    try {
      const result = await send(values, requestId);
      draft.receipt = result.file;
      return true;
    } catch (error) {
      draft.error = `No se pudo registrar «${values.relative_path}»: ${error.message}`;
      return false;
    } finally { draft.saving = false; }
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
          ...(f.external ? {external:true, input_readonly:true, source_path:f.source_path} : {}),
        });
      }
      out.view = { page: "project", object_id: p.id, area: area || "shared" };
    }
    if (editor) out.view.editor = editor;
    return out;
  }

  // Export the original response text, not a re-serialization of JS numbers:
  // native filesystem timestamps can exceed Number.MAX_SAFE_INTEGER.
  async function referenceSnapshot(fetcher, projectId, fileIds) {
    const response = await fetcher("/api/agent/call", {
      method:"POST", credentials:"same-origin", headers:{"Content-Type":"application/json"},
      body:JSON.stringify({name:"atlas_context", arguments:{project_id:projectId, file_ids:[...fileIds]}}),
    });
    const raw = await response.text();
    const envelope = JSON.parse(raw);
    if (!response.ok || envelope.ok === false) throw new Error(envelope.error || "No se pudieron preparar las referencias. Prueba de nuevo.");
    return {raw, context:envelope.result.context};
  }

  const api = { changedFields, projectDraft, refreshProjectDraft, editProjectDraft, fileDraft, editFileDraft, saveFileDraft, editorContext, debounced, buildContext, referenceSnapshot };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.atlasCopilotContext = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
