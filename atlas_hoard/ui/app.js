"use strict";
const $ = (s) => document.querySelector(s);
let projects = [], selected = null, area = "shared", activeProject = null, loadGeneration = 0;
let projectTab = "files";
let projectFilters = {query:"",state:"",sphere:""}, projectFilterGeneration = 0, projectFilterTimer;
let projectEditorOpen = false, projectEditorElement = null;
const projectDrafts = new Map();
const referenceDrafts = new Map();
const fileDrafts = new Map();
let searchState = {query: "", area: "all", availability: "all", result: null}, searchGeneration = 0;
const labels = {faustus:"Faustus",writer:"Writer",lumiere:"Lumiere",prospero:"Prospero",borges:"Borges",kafka:"Kafka",daguerre:"Daguerre",scheherazade:"Scheherazade"};
const appName = (id) => labels[id] || id;
const node = (tag, text, cls) => {const e=document.createElement(tag); if(text!==undefined)e.textContent=text; if(cls)e.className=cls; return e;};
function message(text, error=false) {const el=$("#message");el.textContent=text;el.dataset.error=String(error);el.hidden=!text;}
async function api(path, body) {const res=await fetch(path,{method:body?"POST":"GET",credentials:"same-origin",headers:body?{"Content-Type":"application/json"}:{},body:body?JSON.stringify(body):undefined});const result=await res.json();if(!res.ok||result.ok===false)throw new Error(result.error||"Atlas no pudo completar la operación. Prueba de nuevo.");return result.result||result;}
const call=(name,arguments_)=>api("/api/agent/call",{name:`atlas_${name}`,arguments:arguments_});
async function copy(value) {try{await navigator.clipboard.writeText(value);message("Ruta copiada. Puedes usarla en cualquier aplicación del proyecto.");return true;}catch(e){message("No se pudo copiar. Selecciona la ruta y cópiala con Ctrl+C.",true);return false;}}
function button(text, action, cls) {const b=node("button",text,cls);b.type="button";b.addEventListener("click",action);return b;}
function fileRegistrationPanel(view) {
  const p=view.project, openArea=area, key=JSON.stringify([p.id,openArea]), CC=globalThis.atlasCopilotContext;
  const draft=fileDrafts.get(key)||CC.fileDraft();fileDrafts.set(key,draft);
  const section=node("section",undefined,"file-registration");section.id="file-registration";
  const panel=node("section",undefined,"file-form");panel.id="file-panel";panel.hidden=!draft.open;
  panel.dataset.projectId=p.id;panel.dataset.area=openArea;
  const toggle=button("Registrar archivo",()=>{draft.open=!draft.open;panel.hidden=!draft.open;toggle.setAttribute("aria-expanded",String(draft.open));if(draft.open)input.focus();});
  toggle.setAttribute("aria-expanded",String(draft.open));toggle.setAttribute("aria-controls","file-panel");
  const bar=node("div",undefined,"file-header");bar.append(node("h3",openArea==="shared"?"Archivos compartidos":`Archivos de ${appName(openArea)}`),toggle);section.append(bar);
  const form=node("form");form.setAttribute("aria-label","Registrar archivo interno");
  const label=node("label","Archivo guardado dentro del proyecto"),input=node("input");
  input.id="relative-path";input.name="relative_path";input.required=true;input.value=draft.values.relative_path;
  input.placeholder=openArea==="shared"?"shared/portada.png":`hoards/${openArea}/proyecto`;
  label.append(input,node("small","Ruta del archivo ya guardado. Atlas lee sus bytes para registrar la revisión; no modifica su contenido."));
  const titleLabel=node("label","Título descriptivo (opcional)"),title=node("input");
  title.id="file-title";title.name="title";title.value=draft.values.title;
  titleLabel.append(title,node("small","Identifica el archivo en Atlas; no cambia su nombre ni su ruta. Vacío: se utiliza el nombre del archivo."));
  for(const field of [input,title])field.addEventListener("input",()=>CC.editFileDraft(draft,field.name,field.value));
  const help=node("p","Si esta ruta ya está registrada, se actualiza su revisión y se conservan el título y la aplicación anteriores.","muted wide");
  const actions=node("div",undefined,"form-actions"),submit=node("button",draft.saving?"Registrando…":"Registrar");
  submit.type="submit";submit.disabled=draft.saving;
  actions.append(submit,button("Cancelar",()=>{draft.open=false;panel.hidden=true;toggle.setAttribute("aria-expanded","false");toggle.focus();},"quiet"));
  form.append(label,titleLabel,help,actions);panel.append(form);
  if(draft.error){const error=node("p",draft.error,"state");error.setAttribute("role","alert");panel.append(error);}
  section.append(panel);
  if(draft.receipt){const f=draft.receipt,receipt=node("section",undefined,"registration-receipt");receipt.setAttribute("aria-label","Último registro confirmado");receipt.setAttribute("role","status");receipt.append(node("h3","Registro confirmado"),node("p",f.title),node("p",f.relative_path,"path"),node("p",`Registrado por ${appName(f.app)} · ID ${f.id}`,"muted"));section.append(receipt);}
  form.addEventListener("submit",async e=>{
    e.preventDefault();submit.disabled=true;submit.textContent="Registrando…";
    const ok=await CC.saveFileDraft(draft,async(values,requestId)=>{
      let relative=values.relative_path.trim().replaceAll("\\","/");
      const base=p.path.replaceAll("\\","/")+"/";
      if(relative.toLowerCase().startsWith(base.toLowerCase()))relative=relative.slice(base.length);
      return call("file_register",{project_id:p.id,relative_path:relative,app:openArea==="shared"?p.owner:openArea,title:values.title,request_id:requestId});
    },()=>crypto.randomUUID());
    if(selected!==p.id||area!==openArea||projectTab!=="files"||activeProject?.id!==p.id)return;
    const focus=captureFileDraft();$("#file-registration")?.replaceWith(fileRegistrationPanel(view));restoreFileDraft(focus);
    if(ok)await refreshInPlace();
  });
  return section;
}
function captureProjectEditorFocus() {
  const field=document.activeElement;
  if(!projectEditorElement?.contains(field)||!field.name)return null;
  return {name:field.name,start:field.selectionStart,end:field.selectionEnd};
}
function restoreProjectEditorFocus(focus) {
  if(!focus||!projectEditorElement)return;
  const field=projectEditorElement.querySelector(`[name="${focus.name}"]`);
  if(!field)return;
  field.focus();try{field.setSelectionRange(focus.start,focus.end);}catch(e){}
}
function projectEditorPanel(project) {
  const CC=globalThis.atlasCopilotContext;
  const draft=projectDrafts.get(project.id)||CC.projectDraft(project);
  projectDrafts.set(project.id,draft);CC.refreshProjectDraft(draft,project);
  const panel=node("section",undefined,"project-editor");panel.setAttribute("aria-label","Editar proyecto");
  panel.append(node("h3","Datos del proyecto"));
  const facts=node("dl",undefined,"project-facts");
  for(const [label,value] of [["Responsable",`${appName(project.owner)} (${project.owner})`],["Ámbito",({personal:"Personal",work:"Trabajo",freelance:"Autónomo"})[project.sphere]||project.sphere],["Carpeta del proyecto",project.path]]){
    facts.append(node("dt",label),node("dd",value,label==="Carpeta del proyecto"?"path":undefined));
  }
  panel.append(facts,node("p","Cambiar el nombre no mueve la carpeta. El responsable y las rutas se conservan.","muted"));
  const form=node("form"),fields=node("fieldset",undefined,"project-edit-fields");fields.disabled=draft.saving;
  fields.append(node("legend","Nombre, objetivo y organización"));
  function field(key,label,tag="input",wide=false) {
    const group=node("label",label,wide?"wide":undefined),input=node(tag);input.name=key;input.id=`project-edit-${key}`;
    if(key==="state")for(const [value,text] of [["active","En curso"],["archived","Archivado"]]){const option=node("option",text);option.value=value;input.append(option);}
    input.value=draft.values[key];if(key==="name"){input.required=true;input.maxLength=200;}
    if(key==="goal"){input.rows=3;input.maxLength=2000;}
    input.addEventListener(tag==="select"?"change":"input",()=>CC.editProjectDraft(draft,key,input.value));group.append(input);fields.append(group);return group;
  }
  field("name","Nombre");
  field("members","Otros Hoards que participan").append(node("small",`IDs separados por comas, por ejemplo writer, lumiere. ${project.owner} permanece como responsable.`));
  field("goal","Objetivo (opcional)","textarea",true);
  field("state","Estado","select").append(node("small","Archivar conserva los archivos y permite reactivar el proyecto desde esta misma ficha."));
  fields.append(node("p","Añadir un Hoard prepara su carpeta. Retirarlo restringe su acceso por la API; sus archivos y carpetas se conservan.","wide muted"));
  const actions=node("div",undefined,"form-actions"),submit=node("button",draft.saving?"Guardando…":"Guardar cambios");submit.type="submit";
  actions.append(submit,button("Descartar cambios",()=>{projectDrafts.delete(project.id);projectEditorOpen=false;panel.hidden=true;const toggle=$("#edit-project");if(toggle){toggle.textContent="Editar proyecto";toggle.setAttribute("aria-expanded","false");toggle.focus();}},"quiet"));
  fields.append(actions);form.append(fields);panel.append(form);
  form.addEventListener("submit",async event=>{
    event.preventDefault();const patch={...draft.patch};
    if(!Object.keys(patch).length){message("No hay cambios que guardar.");return;}
    draft.requestId ||= crypto.randomUUID();draft.saving=true;fields.disabled=true;submit.textContent="Guardando…";
    try {
      const result=await call("project_update",{project_id:project.id,...patch,request_id:draft.requestId});
      projectDrafts.delete(project.id);projects=projects.map(p=>p.id===project.id?result.project:p);projectNavigation();
      if(selected===project.id){projectEditorOpen=false;message("Proyecto actualizado. Los archivos siguen en sus rutas.");await refreshInPlace();}
    }catch(error){if(selected===project.id)message(error.message,true);}
    finally{draft.saving=false;fields.disabled=false;submit.textContent="Guardar cambios";if(selected===project.id&&projectEditorElement!==panel){const latest=projectEditorElement?.querySelector("fieldset");if(latest)latest.disabled=false;const latestSubmit=projectEditorElement?.querySelector('[type="submit"]');if(latestSubmit)latestSubmit.textContent="Guardar cambios";}}
  });
  return panel;
}
function drawProjectNavigation(visible) {
  const nav=$("#projects");nav.replaceChildren();
  for(const p of visible){const b=button(p.name,()=>choose(p.id));b.setAttribute("aria-current",String(p.id===selected));b.append(node("small",(p.sphere==="work"?"Trabajo":p.sphere==="freelance"?"Autónomo":"Personal")+(p.state==="archived"?" · Archivado":"")));nav.append(b);}
  if(!visible.length)nav.append(node("p",projects.length?"No hay proyectos con estos filtros.":"Todavía no hay proyectos.","muted"));
  $("#project-filter-status").textContent=`${visible.length} de ${projects.length} proyectos`;
  const outside=selected&&!visible.some(p=>p.id===selected),note=$("#project-filter-selection");
  note.hidden=!outside;note.textContent=outside?`Abierto fuera del filtro: ${activeProject?.name||projects.find(p=>p.id===selected)?.name||"proyecto actual"}.`:"";
}
async function projectNavigation() {
  const generation=++projectFilterGeneration,filters={...projectFilters},nav=$("#projects");
  const filtered=Object.values(filters).some(Boolean);
  nav.setAttribute("aria-busy","true");$("#project-filter-submit").textContent="Filtrar";
  if(filtered)$("#project-filter-status").textContent="Actualizando proyectos…";
  try {
    const visible=filtered?(await call("projects",filters)).projects:projects;
    if(generation!==projectFilterGeneration)return;
    drawProjectNavigation(visible);
  }catch(error){if(generation===projectFilterGeneration){$("#project-filter-status").textContent="No se pudo filtrar. Se conserva la lista anterior; reintenta la consulta.";$("#project-filter-submit").textContent="Reintentar";}}
  finally{if(generation===projectFilterGeneration)nav.removeAttribute("aria-busy");}
}
function updateProjectFilters(delayed=false) {
  projectFilters={query:$("#project-query").value,state:$("#project-state").value,sphere:$("#project-sphere").value};
  ++projectFilterGeneration;clearTimeout(projectFilterTimer);
  if(delayed){$("#projects").setAttribute("aria-busy","true");$("#project-filter-status").textContent="Actualizando proyectos…";projectFilterTimer=setTimeout(projectNavigation,250);}
  else projectNavigation();
}
$("#project-query").addEventListener("input",()=>updateProjectFilters(true));
for(const selector of ["#project-state","#project-sphere"])$(selector).addEventListener("change",()=>updateProjectFilters());
$("#project-filter-form").addEventListener("submit",event=>{event.preventDefault();updateProjectFilters();});
$("#project-filter-reset").addEventListener("click",()=>{$("#project-query").value="";$("#project-state").value="";$("#project-sphere").value="";updateProjectFilters();});
async function choose(id) {invalidateReferences();selected=id;area="shared";projectTab="files";projectEditorOpen=false;searchState={query:"",area:"all",availability:"all",result:null};searchGeneration++;projectNavigation();await showProject();}
async function showProject() {invalidateReferences();if(!selected)return;const requestedId=selected,generation=++loadGeneration;activeProject=null;const loading=node("section",undefined,"empty");loading.append(node("h2","Cargando archivos del proyecto…"));$("#main").replaceChildren(loading);$("#main").setAttribute("aria-busy","true");try{const view=await call("project",{project_id:requestedId});if(generation!==loadGeneration||selected!==requestedId)return;activeProject=view.project;render(view);}catch(e){if(generation===loadGeneration&&selected===requestedId){loading.replaceChildren(node("p","No se pudo abrir el proyecto. Selecciónalo de nuevo para reintentar."));message(e.message,true);}}finally{if(generation===loadGeneration)$("#main").removeAttribute("aria-busy");}}
function icon() {const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");svg.setAttribute("viewBox","0 0 24 28");svg.setAttribute("aria-hidden","true");const path=document.createElementNS(svg.namespaceURI,"path");path.setAttribute("d","M5 2h9l5 5v19H5z M14 2v6h5 M8 13h8 M8 17h8 M8 21h5");svg.append(path);return svg;}
function invalidateReferences() {
  const draft = referenceDrafts.get(selected);
  if (!draft) return;
  draft.generation++; draft.snapshot=null; draft.busy=false; draft.error="";
  draft.paint?.();
}
function referencePanel(view) {
  const project=view.project;
  let draft=referenceDrafts.get(project.id);
  if (!draft) { draft={ids:[],pick:"",open:false,snapshot:null,busy:false,error:"",generation:0}; referenceDrafts.set(project.id,draft); }
  const panel=node("details",undefined,"context-references"); panel.open=draft.open;
  panel.addEventListener("toggle",()=>{draft.open=panel.open;});
  const summary=node("summary","Preparar referencias"); panel.append(summary);
  const body=node("div"); panel.append(body);
  function changeSelection(ids) {
    draft.ids=ids; draft.generation++; draft.snapshot=null; draft.busy=false; draft.error=""; paint();
  }
  function paint() {
    body.replaceChildren();
    body.append(node("p","Elige archivos de todo el proyecto, en el orden que quieras compartirlos. Los filtros y las carpetas no cambian esta selección.","muted"));
    const picker=node("div",undefined,"context-picker"),label=node("label","Archivo registrado"),select=node("select"); select.id="context-file";
    const placeholder=node("option","Selecciona un archivo…"); placeholder.value=""; select.append(placeholder);
    for(const file of view.files.filter(file=>!draft.ids.includes(file.id))) {
      const option=node("option",`${file.title} · ${file.relative_path||file.path}${file.external?" · Externo, sólo lectura":""}${file.exists?"":" · No encontrado"}`);
      option.value=file.id; select.append(option);
    }
    select.value=draft.pick; select.addEventListener("change",()=>{draft.pick=select.value;add.disabled=!draft.pick||draft.ids.length>=20;});
    label.append(select); const add=button("Añadir a la selección",()=>{if(!draft.pick||draft.ids.length>=20)return;const id=draft.pick;draft.pick="";changeSelection([...draft.ids,id]);});
    add.disabled=!draft.pick||draft.ids.length>=20; picker.append(label,add); body.append(picker);
    body.append(node("p",`${draft.ids.length} de 20 archivos seleccionados`,"context-count"));
    const chosen=node("ol",undefined,"context-selection");
    for(const id of draft.ids) {
      const file=view.files.find(file=>file.id===id),item=node("li"),description=node("div");
      description.append(node("strong",file?.title||`Archivo #${id}`),node("p",file?.relative_path||file?.path||"Ya no figura en este proyecto; retíralo para preparar otra selección.","path"));
      const remove=button("Quitar",()=>changeSelection(draft.ids.filter(value=>value!==id)),"quiet");remove.setAttribute("aria-label",`Quitar ${file?.title||id} de la selección`);
      item.append(description,remove);chosen.append(item);
    }
    body.append(chosen);
    if(!draft.ids.length)body.append(node("p","Sin archivos, se preparan sólo los datos del proyecto.","muted"));
    body.append(node("p","Preparar lee los originales para actualizar hash, tamaño y fecha de modificación de los archivos elegidos. No los modifica ni abre aplicaciones. El JSON contiene referencias y metadatos, no el contenido de los archivos.","context-help muted"));
    const prepare=button(draft.busy?"Preparando referencias…":"Preparar JSON",async()=>{
      const generation=++draft.generation,ids=[...draft.ids]; draft.busy=true;draft.snapshot=null;draft.error="";paint();
      try {
        const snapshot=await globalThis.atlasCopilotContext.referenceSnapshot(fetch,project.id,ids);
        if(generation!==draft.generation||selected!==project.id)return;
        draft.snapshot=snapshot;
      } catch(error) { if(generation===draft.generation&&selected===project.id)draft.error=error.message; }
      finally { if(generation===draft.generation&&selected===project.id){draft.busy=false;draft.paint();} }
    });
    prepare.disabled=draft.busy;body.append(prepare);
    if(draft.error){const error=node("p",draft.error,"reference-feedback");error.setAttribute("role","alert");body.append(error);}
    if(!draft.snapshot)return;
    const snapshot=draft.snapshot,context=snapshot.context,result=node("section",undefined,"context-result");result.setAttribute("aria-label","Referencias preparadas");
    result.append(node("h3","Referencias preparadas"),node("p",`${project.name} · ${context.sphere} · ${context.members.map(appName).join(" · ")}`),node("p",context.goal||"Sin objetivo indicado.","muted"),node("p",`Preparado: ${new Date(context.assembled_at*1000).toLocaleString()}`,"muted"));
    const files=node("ul",undefined,"context-file-summary");
    for(const file of context.files){
      const item=node("li");item.append(node("strong",file.title),node("p",file.path,"path"),node("p",`${file.exists?"En su ruta":"No encontrado; revisión registrada, sin comprobar el original"}${file.external?" · Externo, sólo lectura":""}`,file.exists?"muted":"state"),node("p",`Revisión registrada: ${file.revision}`,"path"));files.append(item);
    }
    result.append(files,node("p","Respuesta JSON nativa completa {ok, tool, result}. Copiar y descargar conservan el mismo texto original, incluidos los enteros de las fechas de modificación.","context-help muted"));
    const actions=node("div",undefined,"form-actions"),feedback=node("p","","reference-feedback");feedback.setAttribute("role","status");
    actions.append(button("Copiar JSON",async()=>{try{await navigator.clipboard.writeText(snapshot.raw);feedback.textContent="JSON de referencias copiado.";}catch(error){feedback.textContent="No se pudo copiar. Abre el texto JSON, selecciónalo y usa Ctrl+C.";}}),button("Descargar JSON",()=>{
      const url=URL.createObjectURL(new Blob([snapshot.raw],{type:"application/json;charset=utf-8"})),link=node("a");link.href=url;link.download=`atlas-referencias-${project.id}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);feedback.textContent="Descarga del JSON iniciada.";
    }));
    const rawDetails=node("details"),rawLabel=node("label","Respuesta JSON de Atlas"),raw=node("textarea");raw.readOnly=true;raw.rows=9;raw.value=snapshot.raw;rawLabel.append(raw);rawDetails.append(node("summary","Ver texto JSON completo"),rawLabel);
    result.append(actions,feedback,rawDetails);body.append(result);
  }
  draft.paint=paint;paint();return panel;
}
function referenceFormSnapshot() {
  const draft=referenceDrafts.get(selected);
  if(projectTab!=="files"||!draft?.open)return null;
  const context=draft.snapshot?.context;
  return {form:"context",mode:"prepare",project_id:selected,fields:{file_ids:[...draft.ids],pending_file_id:draft.pick},preparing:draft.busy,
    ...(context?{prepared:{project_id:context.project_id,assembled_at:context.assembled_at,files:context.files.map(file=>({id:file.id,title:file.title,revision:file.revision,exists:file.exists}))}}:{})};
}
function searchPanel(view) {
  const project = view.project, panel = node("section", undefined, "file-search");
  panel.setAttribute("aria-label", "Buscar archivos del proyecto");
  panel.append(node("h3", "Buscar archivos"), node("p", "Busca por nombre o ruta entre los archivos registrados. No se busca dentro de su contenido.", "muted"));
  const form = node("form", undefined, "search-form"), queryLabel = node("label", "Nombre o ruta"), query = node("input");
  query.type = "search"; query.placeholder = "Ej. portada o informe.pdf"; query.maxLength = 200; query.value = searchState.query;
  query.addEventListener("input", () => { searchState.query = query.value; }); queryLabel.append(query);
  const areaLabel = node("label", "Carpeta"), folder = node("select");
  for (const [value, label] of [["all", "Todo el proyecto"], ["shared", "Compartidos"], ...project.members.map(id => [id, appName(id)])]) {
    const option = node("option", label); option.value = value; folder.append(option);
  }
  folder.value = searchState.area; folder.addEventListener("change", () => { searchState.area = folder.value; }); areaLabel.append(folder);
  const availabilityLabel = node("label", "Disponibilidad"), availability = node("select");
  for (const [value, label] of [["all", "Todos"], ["present", "En su ruta"], ["missing", "No encontrados en disco"]]) {
    const option = node("option", label); option.value = value; availability.append(option);
  }
  availability.value = searchState.availability; availability.addEventListener("change", () => { searchState.availability = availability.value; }); availabilityLabel.append(availability);
  const submit = node("button", "Buscar"); submit.type = "submit";
  const results = node("div", undefined, "search-results"); results.setAttribute("aria-live", "polite");
  const clear = button("Limpiar", () => {
    searchGeneration++; searchState = {query:"",area:"all",availability:"all",result:null};
    query.value=""; folder.value="all"; availability.value="all"; results.replaceChildren(); submit.disabled=false; results.removeAttribute("aria-busy"); query.focus();
  }, "quiet");
  form.append(queryLabel, areaLabel, availabilityLabel, submit, clear); panel.append(form, results);
  function showResults(result) {
    results.replaceChildren();
    results.append(node("p", result.total ? `${result.total} archivo(s) encontrado(s) · ${result.offset + 1}–${Math.min(result.offset + result.limit, result.total)}` : "No hay archivos registrados que coincidan. Prueba otro nombre o cambia los filtros.", "search-count"));
    if (!result.files.length) return;
    const wrap = node("div", undefined, "table-wrap"), table = node("table"), head = node("thead"), header = node("tr");
    for (const label of ["Archivo y carpeta", "Disponibilidad", "Acceso"]) header.append(node("th", label)); head.append(header); table.append(head);
    const body = node("tbody");
    for (const file of result.files) {
      const row = node("tr"), name = node("td"), state = node("td", file.exists ? "En su ruta" : "No encontrado en disco", file.exists ? "muted" : "state"), access = node("td");
      name.append(node("strong", file.title), node("p", file.relative_path || file.source_path));
      if (file.external) name.append(node("p", "Referencia externa · solo lectura"));
      if (!file.exists) name.append(node("p", "No encontrado en disco", "state"));
      access.append(button("Copiar ruta", () => copy(file.path))); row.append(name, state, access); body.append(row);
    }
    table.append(body); wrap.append(table); results.append(wrap);
    const pages = node("div", undefined, "search-pages");
    if (result.offset) pages.append(button("Anterior", () => run({...result, offset: Math.max(0,result.offset-result.limit)})));
    if (result.has_more) pages.append(button("Siguiente", () => run({...result, offset: result.offset+result.limit})));
    results.append(pages);
  }
  async function run(filters) {
    const generation = ++searchGeneration; submit.disabled=true; results.setAttribute("aria-busy", "true");
    try {
      const result = await call("files_search", {project_id:project.id,query:filters.query,area:filters.area,availability:filters.availability,offset:filters.offset || 0,limit:50});
      if (generation !== searchGeneration || selected !== project.id) return;
      searchState.result=result; showResults(result);
    } catch (error) { if (generation === searchGeneration && selected === project.id) message(error.message, true); }
    finally { if (generation === searchGeneration) { submit.disabled=false; results.removeAttribute("aria-busy"); } }
  }
  form.addEventListener("submit", event => { event.preventDefault(); run({...searchState, offset:0}); });
  if (searchState.result) run(searchState.result);
  return panel;
}
function render(view) {const focus=captureProjectEditorFocus();const main=$("#main");main.replaceChildren();projectEditorElement=null;const p=view.project;const title=node("section",undefined,"project-title");const heading=node("div",undefined,"project-heading"),edit=button(projectEditorOpen?"Cerrar edición":"Editar proyecto",async()=>{if(projectEditorOpen){projectEditorOpen=false;if(projectEditorElement)projectEditorElement.hidden=true;edit.textContent="Editar proyecto";edit.setAttribute("aria-expanded","false");return;}projectEditorOpen=true;edit.disabled=true;const updated=await refreshInPlace();if(selected===p.id){if(updated)$("#project-edit-name")?.focus();else{projectEditorOpen=false;message("No se pudieron leer los datos del proyecto. Prueba de nuevo.",true);}}edit.disabled=false;});edit.id="edit-project";edit.setAttribute("aria-expanded",String(projectEditorOpen));heading.append(node("h2",p.name),edit);title.append(heading);if(p.goal)title.append(node("p",p.goal));if(p.state==="archived")title.append(node("p","Proyecto archivado; sus archivos se conservan.","state"));main.append(title);if(projectEditorOpen){projectEditorElement=projectEditorPanel(p);main.append(projectEditorElement);restoreProjectEditorFocus(focus);}const tabs=node("nav",undefined,"folders");tabs.setAttribute("aria-label","Vistas del proyecto");for(const [key,label] of [["files","Archivos"],["results","Resultados reutilizables"]]){const b=button(label,()=>{projectTab=key;render(view);});b.setAttribute("aria-pressed",String(projectTab===key));tabs.append(b);}main.append(tabs);if(projectTab==="results"){main.append(globalThis.atlasDerivedResults.create({view,call,message,copy}));return;}main.append(referencePanel(view),searchPanel(view));
const folders=node("nav",undefined,"folders");folders.setAttribute("aria-label","Carpetas del proyecto");for(const [key,label] of [["shared","Compartidos"],...p.members.map(a=>[a,appName(a)])]){const b=button(label,()=>{area=key;render(view);});b.setAttribute("aria-pressed",String(area===key));folders.append(b);}main.append(folders);
const folder=area==="shared"?p.shared_path:p.hoard_paths[area];const location=node("section",undefined,"location");location.setAttribute("aria-label","Ruta de la carpeta seleccionada");location.append(node("p",folder,"path"),button("Copiar ruta",()=>copy(folder)));main.append(location);
main.append(fileRegistrationPanel(view));
const prefix=area==="shared"?"shared/":`hoards/${area}/`;const files=view.files.filter(f=>(f.relative_path || "").startsWith(prefix));if(files.length){const wrap=node("div",undefined,"table-wrap"),table=node("table"),head=node("thead"),hr=node("tr");for(const h of ["Archivo","Registrado por","Acceso"])hr.append(node("th",h));head.append(hr);table.append(head);const body=node("tbody");for(const f of files){const row=node("tr"),name=node("td"),line=node("div",undefined,"file-name");const details=node("div");details.append(node("strong",f.title),node("p",f.relative_path));if(!f.exists)details.append(node("p","El archivo no está en su ruta. Comprueba si lo has movido.","state"));line.append(icon(),details);name.append(line);const app=node("td",appName(f.app),"muted"),access=node("td");access.append(button("Copiar ruta",()=>copy(f.path)));row.append(name,app,access);body.append(row);}table.append(body);wrap.append(table);main.append(wrap);}else{const empty=node("section",undefined,"folder-empty");empty.append(node("h3","Esta carpeta está lista para usar"),node("p","Guarda aquí un PNG, un documento o el proyecto nativo de tu aplicación. Después regístralo para que los demás Hoards puedan encontrarlo."));main.append(empty);}
main.append(globalThis.atlasExternalReferences.create({view,call,copy,refresh:refreshInPlace}));
const members=node("section",undefined,"members");members.append(node("h3","Trabajan en este proyecto"),node("p",p.members.map(appName).join(" · ")),node("p","Los archivos compartidos son originales de trabajo. Si los editas en otra aplicación, el cambio se ve en la misma ruta."));main.append(members);}
async function refresh() {try{const status=await api("/api/status");projects=status.projects;$("#disk-root").textContent=status.root;projectNavigation();if(projects.length&&!selected)selected=projects[0].id;if(selected){projectNavigation();await showProject();}}catch(e){message("No se pudo leer el disco compartido. "+e.message,true);}}
$("#new-project").addEventListener("click",()=>{$("#create-panel").hidden=false;$("#create-form input").focus();});$("#cancel-create").addEventListener("click",()=>{$("#create-panel").hidden=true;});
$("#create-form").addEventListener("input",e=>{delete e.currentTarget.dataset.requestId;});
$("#create-form").addEventListener("submit",async e=>{e.preventDefault();const form=e.currentTarget,submit=form.querySelector('[type="submit"]');submit.disabled=true;try{const values=Object.fromEntries(new FormData(form));const members=[...new Set([values.owner.trim().toLowerCase(),...values.members.split(",").map(s=>s.trim().toLowerCase()).filter(Boolean)])];form.dataset.requestId ||= crypto.randomUUID();const result=await call("project_create",{name:values.name,owner:values.owner.trim().toLowerCase(),members,sphere:values.sphere,goal:values.goal,request_id:form.dataset.requestId});selected=result.project.id;area="shared";projectEditorOpen=false;$("#create-panel").hidden=true;form.reset();delete form.dataset.requestId;message("Proyecto creado. Copia la ruta de su carpeta y empieza a guardar archivos allí.");await refresh();}catch(err){message(err.message,true);}finally{submit.disabled=false;}});
// --- Family assistant contract: real context of the open view and in-place refresh ---
const CREATE_DEFAULTS = {name: "", owner: "faustus", members: "", sphere: "personal", goal: ""};
function captureFileDraft() {const panel=$("#file-panel");if(!panel||panel.hidden)return null;const field=document.activeElement;return {projectId:panel.dataset.projectId,area:panel.dataset.area,focused:panel.contains(field)?field.name:null,start:field?.selectionStart,end:field?.selectionEnd};}
function restoreFileDraft(draft) {if(!draft)return;const panel=$("#file-panel");if(!panel||panel.dataset.projectId!==draft.projectId||panel.dataset.area!==draft.area)return;const field=draft.focused&&panel.querySelector(`[name="${draft.focused}"]`);if(field){field.focus();try{field.setSelectionRange(draft.start,draft.end);}catch(e){}}}
async function refreshInPlace() {
  invalidateReferences();
  const requestedId=selected,generation=loadGeneration;
  try {
    const status = await api("/api/status");
    if(generation!==loadGeneration||selected!==requestedId)return false;
    projects = status.projects; $("#disk-root").textContent = status.root; projectNavigation();
    if (!requestedId) return;
    const view = await call("project", {project_id: requestedId});
    if (generation !== loadGeneration || selected !== requestedId) return;
    if (area !== "shared" && !view.project.members.includes(area)) area = "shared";
    const draft = captureFileDraft();
    activeProject = view.project; render(view); restoreFileDraft(draft);
    return true;
  } catch (e) { /* keep the current view; the next turn refreshes again */ return false; }
}
function createFormSnapshot() {
  const panel = $("#create-panel"); if (!panel || panel.hidden) return null;
  const values = Object.fromEntries(new FormData($("#create-form")));
  return {form: "project_create", mode: "create", fields: globalThis.atlasCopilotContext.changedFields(CREATE_DEFAULTS, values)};
}
function fileFormSnapshot() {
  const panel = $("#file-panel"), draft=fileDrafts.get(JSON.stringify([selected,area]));if(!panel||panel.hidden||!draft)return null;
  return {form:"file_register",mode:"create",project_id:selected,area,fields:globalThis.atlasCopilotContext.changedFields({relative_path:"",title:""},draft.values),saving:draft.saving,...(draft.receipt?{confirmed:{id:draft.receipt.id,title:draft.receipt.title,relative_path:draft.receipt.relative_path,app:draft.receipt.app}}:{})};
}
function projectFormSnapshot() {
  const draft=projectDrafts.get(selected);if(!projectEditorOpen||!projectEditorElement?.isConnected||projectEditorElement.hidden||!draft||!Object.keys(draft.patch).length)return null;
  return {form:"project_update",mode:"edit",project_id:selected,fields:draft.patch};
}
async function copilotContext() {
  const CC = globalThis.atlasCopilotContext;
  try {
    // Everything mutable is captured before the first await: navigating while the fetch is pending must not mix two views.
    const openId = selected, openArea = area, openTab = projectTab;
    const openProjectFilters = {...projectFilters};
    const openSearch = searchState.result && {query:searchState.result.query,area:searchState.result.area,availability:searchState.result.availability,total:searchState.result.total};
    const editor = CC.editorContext(window);
    let view = null;
    if (openId) { try { view = await call("project", {project_id: openId}); } catch (e) { view = null; } }
    const prefix = openArea === "shared" ? "shared/" : `hoards/${openArea}/`;
    const files = view && Array.isArray(view.files) ? view.files.filter(f => (f.relative_path || "").startsWith(prefix) || (openTab === "files" && f.external)) : [];
    const context = CC.buildContext({view, area: openArea, files, editor});
    context.view.project_tab = openTab;
    context.view.project_filters = openProjectFilters;
    if (openSearch && openTab === "files") context.view.search = openSearch;
    return context;
  } catch (e) { return {active_objects: [], view: {page: "home"}}; }
}
if (typeof window !== "undefined" && globalThis.atlasCopilotContext) {
  window.addEventListener("atlas:context-request", e => {
    for (const snapshot of [createFormSnapshot(), fileFormSnapshot(), projectFormSnapshot(), referenceFormSnapshot(), globalThis.atlasExternalReferences.snapshot()]) if (snapshot) e.detail.provide(snapshot);
  });
  const scheduleRefresh = globalThis.atlasCopilotContext.debounced(refreshInPlace, 250);
  window.addEventListener("hoard:copilot-turn-end", scheduleRefresh);
  window.hoardCopilot = {context: copilotContext, onTurnEnd: scheduleRefresh};
}
refresh();
