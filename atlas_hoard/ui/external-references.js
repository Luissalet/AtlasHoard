"use strict";
// Project-wide read-only inputs, backed by Atlas's existing file tools.
(function (root) {
  const drafts = new Map(), checks = new Map();
  let activePanel = null, activeDraft = null, activeProject = null;
  const node = (tag, text, cls) => { const el=document.createElement(tag); if(text!==undefined)el.textContent=text; if(cls)el.className=cls; return el; };
  const defaults = project => ({source_path:"", title:"", app:project.owner});
  function snapshot() {
    if (!activePanel?.isConnected || !activeDraft?.open) return null;
    return {form:"file_link_source", mode:"create", project_id:activeProject, fields:{...activeDraft.values}};
  }
  function create({view, call, copy, refresh}) {
    const project=view.project;
    let draft=drafts.get(project.id);
    if(!draft){draft={values:defaults(project),open:false,saving:false,requestId:null,error:""};drafts.set(project.id,draft);}
    const panel=node("section",undefined,"external-references");panel.setAttribute("aria-label","Referencias externas del proyecto");
    activePanel=panel;activeDraft=draft;activeProject=project.id;
    const isCurrent=()=>activeProject===project.id&&activePanel?.isConnected;
    const heading=node("div",undefined,"file-header"),toggle=node("button",draft.open?"Cerrar formulario":"Añadir referencia externa");toggle.type="button";
    toggle.setAttribute("aria-expanded",String(draft.open));toggle.setAttribute("aria-controls","external-reference-form");
    heading.append(node("h3","Referencias externas del proyecto"),toggle);
    panel.append(heading,node("p","Entradas de sólo lectura que permanecen en su carpeta original. Se muestran en todo el proyecto, independientemente de la carpeta seleccionada.","muted"));
    const form=node("form");form.id="external-reference-form";form.hidden=!draft.open;
    const fields=node("fieldset",undefined,"reference-fields");fields.disabled=draft.saving;
    function field(key,label,tag="input",wide=false){
      const group=node("label",label,wide?"wide":undefined),input=node(tag);input.name=key;
      if(tag==="select")for(const member of project.members){const option=node("option",member);option.value=member;input.append(option);}
      if(key==="app"&&!project.members.includes(draft.values.app)){const old=node("option",draft.values.app+" (ya no participa)");old.value=draft.values.app;input.append(old);}
      input.value=draft.values[key];if(key==="source_path"){input.required=true;input.placeholder="D:\\Documentos\\referencia.txt";}
      if(key==="title")input.maxLength=200;
      input.addEventListener(tag==="select"?"change":"input",()=>{draft.values[key]=input.value;draft.requestId=null;});
      group.append(input);fields.append(group);return input;
    }
    const source=field("source_path","Ruta absoluta del archivo original","input",true);
    const titleInput=field("title","Título (opcional)"),appInput=field("app","Hoard asociado","select");
    fields.append(node("p","Registrar y Comprobar leen el archivo para calcular hash, tamaño y fecha de modificación. No lo copian, modifican ni ejecutan, y no abren ninguna aplicación.","wide muted"));
    const actions=node("div",undefined,"form-actions"),submit=node("button",draft.saving?"Añadiendo…":"Añadir referencia");submit.type="submit";
    const discard=node("button","Descartar borrador","quiet");discard.type="button";
    discard.addEventListener("click",()=>{draft.values=defaults(project);draft.requestId=null;draft.error="";draft.open=false;source.value="";titleInput.value="";appInput.value=project.owner;error.hidden=true;form.hidden=true;toggle.textContent="Añadir referencia externa";toggle.setAttribute("aria-expanded","false");toggle.focus();});
    actions.append(submit,discard);fields.append(actions);form.append(fields);
    const error=node("p",draft.error,"reference-feedback");error.setAttribute("role","alert");error.hidden=!draft.error;form.append(error);panel.append(form);
    toggle.addEventListener("click",()=>{draft.open=!draft.open;form.hidden=!draft.open;toggle.textContent=draft.open?"Cerrar formulario":"Añadir referencia externa";toggle.setAttribute("aria-expanded",String(draft.open));if(draft.open)source.focus();});
    form.addEventListener("submit",async event=>{
      event.preventDefault();draft.saving=true;draft.error="";error.hidden=true;fields.disabled=true;submit.textContent="Añadiendo…";
      draft.requestId ||= crypto.randomUUID();
      try{
        const args={project_id:project.id,source_path:draft.values.source_path,app:draft.values.app,request_id:draft.requestId};
        if(draft.values.title.trim())args.title=draft.values.title.trim();
        const result=await call("file_link_source",args);
        checks.set(result.file.id,{text:"Referencia registrada. El original permanece en su ruta.",busy:false});
        draft.values=defaults(project);draft.open=false;draft.requestId=null;
        if(isCurrent())await refresh();
      }catch(failure){draft.error=failure.message;if(isCurrent()){const current=activePanel.querySelector('[role="alert"]');current.textContent=draft.error;current.hidden=false;}}
      finally{
        draft.saving=false;
        if(isCurrent()){activePanel.querySelector("fieldset").disabled=false;activePanel.querySelector('[type="submit"]').textContent="Añadir referencia";}
      }
    });
    const references=view.files.filter(file=>file.external);
    if(!references.length)panel.append(node("p","Todavía no hay referencias externas registradas en este proyecto.","reference-empty muted"));
    const list=node("ul",undefined,"reference-list");
    for(const file of references){
      const item=node("li"),top=node("div",undefined,"reference-title");
      top.append(node("h4",file.title),node("span","Sólo lectura","muted"));item.append(top,node("p",file.source_path||file.path,"path"));
      item.append(node("p",`${file.app} · ${file.exists?"En su ruta":"No encontrado en disco"}`,file.exists?"muted":"state"));
      const revision=node("p","Revisión registrada: ");revision.append(node("span",file.revision,"path"));item.append(revision,node("p",`Tamaño registrado: ${file.size} bytes. Usa Comprobar para actualizar estos metadatos.`,"muted"));
      const feedback=node("p",checks.get(file.id)?.text||"","reference-feedback");feedback.setAttribute("role","status");
      const buttons=node("div",undefined,"reference-actions"),copyButton=node("button","Copiar ruta original"),check=node("button",checks.get(file.id)?.busy?"Comprobando…":"Comprobar");
      copyButton.type=check.type="button";check.dataset.fileId=file.id;check.disabled=!!checks.get(file.id)?.busy;
      copyButton.addEventListener("click",async()=>{const ok=await copy(file.source_path||file.path);feedback.textContent=ok?"Ruta original copiada.":"No se pudo copiar. Selecciona la ruta y usa Ctrl+C.";});
      check.addEventListener("click",async()=>{
        checks.set(file.id,{text:"Comprobando el archivo original…",busy:true});feedback.textContent=checks.get(file.id).text;check.disabled=true;check.textContent="Comprobando…";
        try{
          const result=await call("file_resolve",{file_id:file.id});
          checks.set(file.id,{busy:false,text:!result.file.exists?"No encontrado en disco. Se conserva la revisión registrada.":result.changed?"El original ha cambiado. Revisión y metadatos actualizados.":"Comprobado. La revisión del original coincide con la registrada."});
          if(isCurrent())await refresh();
        }catch(failure){checks.set(file.id,{busy:false,text:failure.message});feedback.textContent=failure.message;}
        finally{check.disabled=false;check.textContent="Comprobar";if(isCurrent()){const current=activePanel.querySelector(`[data-file-id="${file.id}"]`);if(current){current.disabled=false;current.textContent="Comprobar";}}}
      });
      buttons.append(copyButton,check);item.append(buttons,feedback);list.append(item);
    }
    panel.append(list);return panel;
  }
  root.atlasExternalReferences={create,snapshot};
})(typeof globalThis!=="undefined"?globalThis:this);
