"use strict";
(function (root) {
  const drafts = new Map();
  let openPanel = null;
  const defaults = () => ({output_id:"", source_ids:[], operation:"", version:"", model_revision:"", options:"{}"});
  const el = (tag, text, cls) => {const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const action = (text, run) => {const b=el("button",text);b.type="button";b.addEventListener("click",run);return b;};
  function create({view, call, message, copy}) {
    const p=view.project, panel=el("section",undefined,"derived-panel");
    const draft=drafts.get(p.id)||defaults();drafts.set(p.id,draft);
    openPanel={panel, project_id:p.id, draft};
    const heading=el("div",undefined,"file-header"), formPanel=el("section",undefined,"derived-form");
    heading.append(el("h3","Resultados reutilizables"),action("Registrar resultado",()=>{formPanel.hidden=!formPanel.hidden;if(!formPanel.hidden)output.focus();}));
    panel.append(heading,el("p","Consulta qué archivos y receta produjeron cada salida. Comprueba sus revisiones actuales antes de reutilizarla.","muted"));
    const list=el("div",undefined,"derived-list");list.setAttribute("aria-live","polite");
    const form=el("form"), output=el("select");output.required=true;
    const label=(text,control,wide=false)=>{const n=el("label",text,wide?"wide":undefined);n.append(control);return n;};
    output.append(new Option("Selecciona la salida ya registrada", ""));
    for(const f of view.files.filter(f=>!f.external&&f.exists))output.append(new Option(`${f.title} · ${f.relative_path}`,f.id));
    output.value=draft.output_id;output.addEventListener("change",()=>{draft.output_id=output.value;syncSources();});
    const sources=el("fieldset",undefined,"derived-sources wide");sources.append(el("legend","Archivos de origen"));
    const choices=[];
    for(const f of view.files.filter(f=>f.exists)){
      const check=el("input");check.type="checkbox";check.value=f.id;check.checked=draft.source_ids.includes(f.id);
      const line=label(`${f.title} · ${f.relative_path||f.source_path}`,check);line.className="derived-source";line.prepend(check);
      check.addEventListener("change",()=>{draft.source_ids=choices.filter(c=>c.checked).map(c=>c.value);});
      choices.push(check);sources.append(line);
    }
    function syncSources(){for(const c of choices){c.disabled=c.value===output.value;if(c.disabled)c.checked=false;}draft.source_ids=choices.filter(c=>c.checked).map(c=>c.value);}
    syncSources();
    const field=(key,text,required=false)=>{const input=el("input");input.value=draft[key];input.required=required;input.name=key;input.addEventListener("input",()=>{draft[key]=input.value;});return label(text,input);};
    const advanced=el("details",undefined,"wide"), options=el("textarea");options.rows=4;options.value=draft.options;options.addEventListener("input",()=>{draft.options=options.value;});
    advanced.append(el("summary","Modelo y opciones (opcional)"),field("model_revision","Revisión del modelo"),label("Opciones de la receta (objeto JSON)",options));
    const actions=el("div",undefined,"form-actions"), submit=el("button","Registrar revisiones actuales");submit.type="submit";
    actions.append(submit,action("Cancelar",()=>{formPanel.hidden=true;}));
    form.append(label("Archivo de salida",output,true),sources,field("operation","Operación",true),field("version","Versión de la operación",true),advanced,
      el("p","Declara que esta salida se obtuvo con la versión actual de los orígenes. Si cambiaron desde que la generaste, vuelve a generarla antes. Atlas registra la relación; no ejecuta la operación.","wide muted"),actions);
    formPanel.append(form);formPanel.hidden=!Object.entries(draft).some(([k,v])=>JSON.stringify(v)!==JSON.stringify(defaults()[k]));
    panel.append(formPanel,list);
    async function load(){
      list.setAttribute("aria-busy","true");
      try {
        const result=await call("derived_results",{project_id:p.id});list.replaceChildren();
        if(!result.results.length)list.append(el("p","Todavía no hay resultados registrados. Guarda y registra tu salida en Archivos; después vincúlala aquí con sus orígenes y receta.","folder-empty"));
        for(const row of result.results)list.append(resultRow(row));
      } catch(e){list.replaceChildren(el("p",e.message,"state"),action("Reintentar",load));}
      finally{list.removeAttribute("aria-busy");}
    }
    function resultRow(row){
      const item=el("article",undefined,"derived-result"), title=el("div",undefined,"derived-heading");
      const status=el("p","Pendiente de comprobar","state");status.setAttribute("role","status");
      title.append(el("h3",row.output.title),status);item.append(title,el("p",`${row.recipe.operation} · versión ${row.recipe.version}`,"muted"),el("p",`Registrado: ${new Date(row.created*1000).toLocaleString()}`,"muted"));
      const details=el("details");details.append(el("summary","Ver orígenes y receta"));
      const provenance=el("dl",undefined,"derived-provenance");
      const entry=(name,text)=>provenance.append(el("dt",name),el("dd",text,"path"));
      entry("Salida",row.output.path);entry("Revisión de salida registrada",row.output_revision);
      for(const s of row.source_revisions){const f=row.sources.find(f=>f.id===s.id);entry(`Origen · ${f.title}`,f.path);entry("Revisión de origen registrada",s.revision);}
      entry("Receta completa",JSON.stringify(row.recipe,null,2));details.append(provenance);item.append(details);
      const controls=el("div",undefined,"form-actions"), check=action("Comprobar ahora",async()=>{
        check.disabled=true;status.textContent="Comprobando archivos…";
        try{
          const result=await call("derived_lookup",{project_id:p.id,source_ids:row.source_revisions.map(s=>s.id),recipe:row.recipe});
          const reusable=result.hit&&result.cache_key===row.cache_key&&result.file.id===row.output.id&&result.file.revision===row.output_revision;
          status.textContent=`${reusable?"Reutilizable: coinciden las revisiones":"No reutilizable con las revisiones actuales"} · comprobado ${new Date().toLocaleTimeString()}`;
          status.className=reusable?"derived-valid":"state";
        } catch(e){status.textContent=`No se pudo comprobar: ${e.message}`;status.className="state";}
        finally{check.disabled=false;}
      });controls.append(check,action("Copiar ruta de salida",()=>copy(row.output.path)));item.append(controls);return item;
    }
    form.addEventListener("submit",async event=>{
      event.preventDefault();submit.disabled=true;
      try{
        if(!draft.source_ids.length)throw new Error("Selecciona al menos un archivo de origen.");
        const optionsValue=JSON.parse(draft.options||"{}");if(!optionsValue||typeof optionsValue!=="object"||Array.isArray(optionsValue))throw new Error("Las opciones deben ser un objeto JSON.");
        const recipe={operation:draft.operation.trim(),version:draft.version.trim()};
        if(draft.model_revision.trim())recipe.model_revision=draft.model_revision.trim();if(Object.keys(optionsValue).length)recipe.options=optionsValue;
        const output_id=draft.output_id, source_ids=[...draft.source_ids];
        const resolved=await Promise.all(source_ids.map(file_id=>call("file_resolve",{file_id})));
        await call("derived_publish",{project_id:p.id,output_id,source_ids,source_revisions:Object.fromEntries(resolved.map(r=>[r.file.id,r.file.revision])),recipe});
        Object.assign(draft,defaults());form.reset();options.value="{}";for(const c of choices)c.checked=false;syncSources();formPanel.hidden=true;
        if(panel.isConnected)message("Resultado registrado. Compruébalo antes de reutilizarlo.");await load();
      }catch(e){if(panel.isConnected)message(e.message,true);}finally{submit.disabled=false;}
    });
    load();return panel;
  }
  root.addEventListener("atlas:context-request",event=>{
    if(!openPanel||!openPanel.panel.isConnected)return;
    const fields=Object.fromEntries(Object.entries(openPanel.draft).filter(([key,value])=>JSON.stringify(value)!==JSON.stringify(defaults()[key])));
    if(Object.keys(fields).length)event.detail.provide({form:"derived-result",mode:"create",project_id:openPanel.project_id,fields});
  });
  root.atlasDerivedResults={create};
})(window);
