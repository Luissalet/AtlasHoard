import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

test('external reference UI preserves drafts on error/view changes and follows native check/copy results',async()=>{
  const document={activeElement:null};
  class Element{
    constructor(tag){this.tag=tag;this.children=[];this.attributes={};this.dataset={};this.listeners={};this.isConnected=false;}
    append(...items){this.children.push(...items);}
    setAttribute(key,value){this.attributes[key]=String(value);}
    addEventListener(name,fn){this.listeners[name]=fn;}
    focus(){document.activeElement=this;}
    querySelector(selector){return walk(this).find(el=>selector.startsWith('[role=')?el.attributes.role===selector.match(/"([^"]+)"/)[1]:selector.startsWith('[type=')?el.type===selector.match(/"([^"]+)"/)[1]:selector.startsWith('[data-file-id=')?el.dataset.fileId===selector.match(/"([^"]+)"/)[1]:el.tag===selector)||null;}
    async emit(name){await this.listeners[name]?.({preventDefault(){}});}
  }
  document.createElement=tag=>new Element(tag);
  const walk=el=>el.children.flatMap(child=>[child,...walk(child)]);
  const text=el=>[el.textContent||'',...el.children.map(text)].join(' ');
  const context=vm.createContext({document,crypto:{randomUUID:()=> 'qa-request'}});
  vm.runInContext(fs.readFileSync('atlas_hoard/ui/external-references.js','utf8'),context);
  vm.runInContext(fs.readFileSync('atlas_hoard/ui/copilot-context.js','utf8'),context);
  const ui=context.atlasExternalReferences;
  const project={id:'p1',owner:'writer',members:['writer','lumiere']};
  const reference={id:'file1',title:'Fuente QA',external:true,input_readonly:true,source_path:'D:/QA/source.txt',path:'D:/QA/source.txt',app:'writer',revision:'sha256:old',size:4,exists:true};
  const view={project,files:[reference]};
  let panel,fail=true,copied=false;
  const calls=[];
  const args={view,copy:async()=>copied,call:async(name,payload)=>{calls.push({name,payload});if(name==='file_link_source'){if(fail)throw Error('source is already linked to this project');return {file:{id:'file2'}};}reference.revision='sha256:new';return {file:reference,changed:true};},refresh:async()=>{panel.isConnected=false;panel=ui.create(args);panel.isConnected=true;}};
  panel=ui.create(args);panel.isConnected=true;
  const button=(label)=>walk(panel).find(el=>el.tag==='button'&&el.textContent===label);
  const input=(name)=>walk(panel).find(el=>el.name===name);
  await button('Añadir referencia externa').emit('click');
  for(const [name,value]of Object.entries({source_path:'D:/QA/another.txt',title:'Mi referencia',app:'lumiere'})){input(name).value=value;await input(name).emit(name==='app'?'change':'input');}
  await panel.querySelector('form').emit('submit');
  assert.match(text(panel),/already linked/);
  assert.equal(panel.querySelector('fieldset').disabled,false);
  assert.equal(input('source_path').value,'D:/QA/another.txt');
  assert.equal(ui.snapshot().fields.app,'lumiere');
  panel.isConnected=false;assert.equal(ui.snapshot(),null);
  const other=ui.create({...args,view:{project:{...project,id:'p2'},files:[]}});other.isConnected=true;
  assert.equal(ui.snapshot(),null);other.isConnected=false;
  panel=ui.create(args);panel.isConnected=true;
  assert.equal(input('title').value,'Mi referencia');
  assert.match(text(panel),/already linked/);
  fail=false;await panel.querySelector('form').emit('submit');
  assert.equal(ui.snapshot(),null);assert.equal(input('source_path').value,'');
  assert.equal(calls[1].payload.project_id,'p1');assert.equal(calls[1].payload.app,'lumiere');
  await button('Copiar ruta original').emit('click');assert.match(text(panel),/No se pudo copiar/);
  copied=true;await button('Copiar ruta original').emit('click');assert.match(text(panel),/Ruta original copiada/);
  await button('Comprobar').emit('click');
  assert.match(text(panel),/sha256:new/);assert.match(text(panel),/original ha cambiado/);
  assert.equal(button('Comprobar').disabled,false);
  assert.equal(calls.at(-1).name,'file_resolve');
  const ctx=context.atlasCopilotContext.buildContext({view,area:'shared',files:[reference]});
  assert.equal(ctx.active_objects[1].input_readonly,true);
  assert.equal(ctx.active_objects[1].source_path,'D:/QA/source.txt');
});
