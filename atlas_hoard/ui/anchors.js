"use strict";
// Anclas / Anchors: precise places inside registered file revisions, with status per revision.
(function (root) {
  const T = {
    es: {title:"Anclas", intro:"Una ancla apunta a un lugar exacto de un archivo registrado (texto, celdas, página y rectángulo de un PDF…). Atlas la fija a la revisión en que se creó y, cuando el archivo cambia, comprueba si sigue intacta, se movió, cambió o se perdió. Atlas no modifica el archivo.",
      file:"Archivo", pickFile:"Selecciona un archivo registrado", revision:"Revisión", latest:"Última conocida", newAnchor:"Nueva ancla", close:"Cerrar", kind:"Tipo", label:"Nombre", comment:"Comentario (opcional)",
      create:"Crear ancla", empty:"Este archivo todavía no tiene anclas.", noFile:"Elige un archivo para ver sus anclas.", retry:"Reintentar", resolve:"Abrir lugar", copy:"Copiar enlace", addComment:"Comentar",
      commentPh:"Añadir un comentario a la revisión actual", origin:"Creada en la revisión", history:"Historia", comments:"Comentarios", created:"Ancla creada.", resolved:"Lugar resuelto.",
      status:{intact:"Intacta", moved:"Movida", changed:"Cambiada", lost:"Perdida"}, kinds:{text:"Texto", cell:"Celdas", pdf:"PDF (página y rectángulo)", code:"Símbolo de código", image:"Región de imagen", time:"Intervalo de tiempo", mesh:"Pieza 3D"},
      fields:{quote:"Cita exacta del texto", line_start:"Línea inicial", line_end:"Línea final", ref:"Hoja y rango (Hoja1!A1:B3)", page:"Página", x0:"Izquierda (0–1)", y0:"Arriba (0–1)", x1:"Derecha (0–1)", y1:"Abajo (0–1)", symbol:"Símbolo (Clase.método)",
        x:"x (0–1)", y:"y (0–1)", w:"Ancho (0–1)", h:"Alto (0–1)", start:"Inicio (s)", end:"Fin (s)", node:"Nombre del nodo", faces:"Caras (opcional, separadas por comas)"},
      hint:"Los rectángulos son proporciones de la página con el origen arriba a la izquierda.", viewable:"Se puede abrir en el archivo actual", notViewable:"Esa revisión ya no es el archivo en disco"},
    en: {title:"Anchors", intro:"An anchor points to an exact place inside a registered file (text, cells, a PDF page and rectangle…). Atlas pins it to the revision it was made on and, when the file changes, checks whether it is still intact, moved, changed or lost. Atlas never edits the file.",
      file:"File", pickFile:"Select a registered file", revision:"Revision", latest:"Latest known", newAnchor:"New anchor", close:"Close", kind:"Type", label:"Name", comment:"Comment (optional)",
      create:"Create anchor", empty:"This file has no anchors yet.", noFile:"Choose a file to see its anchors.", retry:"Retry", resolve:"Open place", copy:"Copy link", addComment:"Comment",
      commentPh:"Add a comment on the current revision", origin:"Made on revision", history:"History", comments:"Comments", created:"Anchor created.", resolved:"Place resolved.",
      status:{intact:"Intact", moved:"Moved", changed:"Changed", lost:"Lost"}, kinds:{text:"Text", cell:"Cells", pdf:"PDF (page and rectangle)", code:"Code symbol", image:"Image region", time:"Time range", mesh:"3D part"},
      fields:{quote:"Exact quote", line_start:"First line", line_end:"Last line", ref:"Sheet and range (Sheet1!A1:B3)", page:"Page", x0:"Left (0–1)", y0:"Top (0–1)", x1:"Right (0–1)", y1:"Bottom (0–1)", symbol:"Symbol (Class.method)",
        x:"x (0–1)", y:"y (0–1)", w:"Width (0–1)", h:"Height (0–1)", start:"Start (s)", end:"End (s)", node:"Node name", faces:"Faces (optional, comma separated)"},
      hint:"Rectangles are page fractions with the origin at the top left.", viewable:"Can be opened in the current file", notViewable:"That revision is no longer the file on disk"}
  };
  const lang = (typeof navigator !== "undefined" && /^en/i.test(navigator.language || "")) ? "en" : "es";
  const t = T[lang];
  const FORMS = {text:["quote", "line_start", "line_end"], cell:["ref"], pdf:["page", "x0", "y0", "x1", "y1"], code:["symbol"], image:["x", "y", "w", "h"], time:["start", "end"], mesh:["node", "faces"]};
  const drafts = new Map();
  const el = (tag, text, cls) => {const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const btn = (text, run) => {const b=el("button",text);b.type="button";b.addEventListener("click",run);return b;};
  const num = v => (v===""||v===undefined)?undefined:Number(v);

  // Builds the selector sent to atlas_anchor_create from the form fields.
  function selectorFrom(kind, v) {
    if (kind==="text") return v.quote ? {quote:v.quote} : {line_start:num(v.line_start), line_end:num(v.line_end)||num(v.line_start)};
    if (kind==="cell") return {ref:v.ref};
    if (kind==="pdf") return {page:num(v.page), rect:[num(v.x0), num(v.y0), num(v.x1), num(v.y1)]};
    if (kind==="code") return {symbol:v.symbol};
    if (kind==="image") return {x:num(v.x), y:num(v.y), w:num(v.w), h:num(v.h)};
    if (kind==="time") return {start:num(v.start), end:num(v.end)};
    const sel = {node:v.node};
    if (v.faces) sel.faces = v.faces.split(",").map(s=>Number(s.trim())).filter(n=>Number.isInteger(n));
    return sel;
  }
  function place(a) {
    const l = a.location;
    if (!l) return "—";
    if (a.kind==="text") return `L${l.line_start}–L${l.line_end}: ${(l.quote||"").slice(0,80)}`;
    if (a.kind==="cell") return l.ref;
    if (a.kind==="pdf") return `p.${l.page} [${l.rect.join(", ")}]`;
    if (a.kind==="code") return `${l.symbol} L${l.line_start}–L${l.line_end}`;
    if (a.kind==="time") return `${l.start}s–${l.end}s`;
    if (a.kind==="image") return `[${l.rect.join(", ")}]`;
    return String(l.node ?? l.node_index);
  }

  function create({view, call, message, copy}) {
    const p = view.project, panel = el("section", undefined, "anchor-panel");
    let draft = drafts.get(p.id);
    if (!draft) {draft = {file_id:"", revision:"", open:false, kind:"text", values:{}, label:"", comment:""};drafts.set(p.id, draft);}
    const heading = el("div", undefined, "file-header");
    const toggle = btn(draft.open ? t.close : t.newAnchor, () => {draft.open = !draft.open; form.hidden = !draft.open; toggle.textContent = draft.open ? t.close : t.newAnchor;});
    heading.append(el("h3", t.title), toggle);
    panel.append(heading, el("p", t.intro, "muted"));
    const label = (text, control, wide) => {const n = el("label", text, wide ? "wide" : undefined); n.append(control); return n;};
    const fileSel = el("select");
    fileSel.append(new Option(t.pickFile, ""));
    for (const f of view.files.filter(f => f.exists)) fileSel.append(new Option(`${f.title} · ${f.relative_path || f.source_path}`, f.id));
    if (!view.files.some(f => f.id === draft.file_id)) draft.file_id = "";
    fileSel.value = draft.file_id;
    const revSel = el("select");
    const controls = el("div", undefined, "anchor-controls");
    controls.append(label(t.file, fileSel), label(t.revision, revSel));
    const list = el("div", undefined, "anchor-list"); list.setAttribute("aria-live", "polite");
    // Create form
    const form = el("form", undefined, "anchor-form"); form.hidden = !draft.open;
    const kindSel = el("select");
    for (const k of Object.keys(FORMS)) kindSel.append(new Option(t.kinds[k], k));
    kindSel.value = draft.kind;
    const dyn = el("div", undefined, "anchor-fields");
    function drawFields() {
      dyn.replaceChildren();
      for (const key of FORMS[draft.kind]) {
        const input = el("input"); input.name = key; input.value = draft.values[key] || "";
        if (key === "quote" || key === "ref" || key === "symbol" || key === "node") input.maxLength = 4000;
        input.addEventListener("input", () => {draft.values[key] = input.value;});
        dyn.append(label(t.fields[key], input, key === "quote" || key === "ref"));
      }
      if (draft.kind === "pdf" || draft.kind === "image") dyn.append(el("p", t.hint, "muted wide"));
    }
    kindSel.addEventListener("change", () => {draft.kind = kindSel.value; draft.values = {}; drawFields();});
    const lab = el("input"); lab.maxLength = 200; lab.value = draft.label; lab.addEventListener("input", () => {draft.label = lab.value;});
    const com = el("input"); com.maxLength = 4000; com.value = draft.comment; com.addEventListener("input", () => {draft.comment = com.value;});
    const submit = el("button", t.create); submit.type = "submit";
    form.append(label(t.kind, kindSel), dyn, label(t.label, lab), label(t.comment, com, true), el("div", undefined, "form-actions"));
    form.lastChild.append(submit);
    drawFields();
    form.addEventListener("submit", async e => {
      e.preventDefault();
      if (!draft.file_id) {message(t.pickFile, true); return;}
      submit.disabled = true;
      try {
        await call("anchor_create", {file_id:draft.file_id, kind:draft.kind, selector:selectorFrom(draft.kind, draft.values), label:draft.label, comment:draft.comment});
        draft.values = {}; draft.label = ""; draft.comment = ""; lab.value = ""; com.value = ""; drawFields();
        message(t.created); await load();
      } catch (err) {message(err.message, true);} finally {submit.disabled = false;}
    });

    async function load() {
      list.setAttribute("aria-busy", "true");
      if (!draft.file_id) {list.replaceChildren(el("p", t.noFile, "folder-empty")); revSel.replaceChildren(new Option(t.latest, "")); list.removeAttribute("aria-busy"); return;}
      try {
        const args = {file_id:draft.file_id};
        if (draft.revision) args.revision = Number(draft.revision);
        const r = await call("anchor_list", args);
        const keep = draft.revision;
        revSel.replaceChildren(new Option(t.latest, ""));
        for (const rev of r.revisions) revSel.append(new Option(`r${rev.seq} · ${rev.revision.slice(7, 15)}`, String(rev.seq)));
        revSel.value = keep;
        list.replaceChildren();
        if (!r.anchors.length) list.append(el("p", t.empty, "folder-empty"));
        for (const a of r.anchors) list.append(row(a));
      } catch (err) {list.replaceChildren(el("p", err.message, "state"), btn(t.retry, load));}
      finally {list.removeAttribute("aria-busy");}
    }
    function row(a) {
      const item = el("article", undefined, "anchor-item"), top = el("div", undefined, "derived-heading");
      const badge = el("span", t.status[a.status], "anchor-status anchor-" + a.status);
      top.append(el("h3", a.label), badge);
      item.append(top, el("p", `${t.kinds[a.kind]} · ${t.origin} r${a.revision_seq} → r${a.status_revision_seq}`, "muted"), el("p", place(a), "path"), el("p", a.detail, "muted"));
      const out = el("div", undefined, "anchor-detail"), actions = el("div", undefined, "form-actions");
      actions.append(btn(t.resolve, async () => {
        try {
          const r = await call("anchor_resolve", {anchor_id:a.id, ...(draft.revision ? {revision:Number(draft.revision)} : {})});
          out.replaceChildren(el("p", r.open.viewable ? t.viewable : t.notViewable, "muted"), el("pre", JSON.stringify(r.open, null, 2), "path"));
          const hist = el("details"); hist.append(el("summary", t.history));
          for (const h of r.history) hist.append(el("p", `r${h.revision_seq} · ${t.status[h.status]} — ${h.detail}`, "muted"));
          for (const c of r.comments) hist.append(el("p", `${t.comments}: r${c.revision_seq} · ${c.author}: ${c.text}`, "muted"));
          out.append(hist); message(t.resolved);
        } catch (err) {message(err.message, true);}
      }), btn(t.copy, () => copy(a.uri)));
      const note = el("input"); note.placeholder = t.commentPh; note.maxLength = 4000;
      actions.append(note, btn(t.addComment, async () => {
        if (!note.value.trim()) return;
        try {await call("anchor_comment", {anchor_id:a.id, text:note.value}); note.value = ""; await load();} catch (err) {message(err.message, true);}
      }));
      item.append(actions, out);
      return item;
    }
    fileSel.addEventListener("change", () => {draft.file_id = fileSel.value; draft.revision = ""; return load();});
    revSel.addEventListener("change", () => {draft.revision = revSel.value; return load();});
    panel.append(controls, form, list);
    load();
    return panel;
  }
  root.atlasAnchors = {create, selectorFrom, place};
})(globalThis);
