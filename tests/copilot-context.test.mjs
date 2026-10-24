import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import { randomUUID } from 'node:crypto';

const require = createRequire(import.meta.url);
const CC = require('../atlas_hoard/ui/copilot-context.js');

test('registration keeps native receipts separate from later drafts, retries and other folders', async () => {
  const a=CC.fileDraft(), b=CC.fileDraft();
  CC.editFileDraft(a,'relative_path','shared/IMG_0042.txt');
  CC.editFileDraft(a,'title','🧭'.repeat(200));
  let finish, sent;
  const pending=CC.saveFileDraft(a,(values,id)=>{sent={values,id};return new Promise(resolve=>{finish=resolve;});},()=> 'first');
  assert.equal(a.saving,true);
  CC.editFileDraft(a,'title','Borrador posterior ñ');
  CC.editFileDraft(b,'title','Otra carpeta');
  finish({file:{id:'registered',title:'Título nativo previo',relative_path:'shared/IMG_0042.txt',app:'lumiere'}});
  assert.equal(await pending,true);
  assert.equal(sent.values.title,'🧭'.repeat(200));
  assert.equal(a.values.title,'Borrador posterior ñ');
  assert.equal(a.receipt.title,'Título nativo previo');
  assert.equal(b.values.title,'Otra carpeta');
  assert.equal(b.receipt,null);
  const ids=[];
  assert.equal(await CC.saveFileDraft(a,async(values,id)=>{ids.push(id);throw new Error('503 ficticio');},()=> 'retry'),false);
  assert.match(a.error,/IMG_0042.txt.*503 ficticio/);
  assert.equal(a.values.title,'Borrador posterior ñ');
  assert.equal(a.receipt.id,'registered');
  assert.equal(await CC.saveFileDraft(a,async(values,id)=>{ids.push(id);return {file:{id:'registered',title:'Título nativo previo'}};},()=>assert.fail('retry must reuse request ID')),true);
  assert.deepEqual(ids,['retry','retry']);
  assert.equal(a.saving,false);
});

test('reference exports keep the native JSON text and unsafe integers without reserializing', async () => {
  const raw = '{"ok": true, "tool": "atlas_context", "result": {"ok": true, "context": {"project_id": "p1", "goal": "Café \\"borrador\\"", "files": [{"id": "f2", "mtime_ns": 1792761234567890123, "path": "C:\\\\ficticio\\\\a.txt"}, {"id": "f1", "mtime_ns": 1792761234567890125}]}}}';
  let request;
  const snapshot = await CC.referenceSnapshot(async (path, options) => {
    request={path, ...options};
    return {ok:true, text:async()=>raw, json:async()=>assert.fail('export must capture the original response text')};
  }, 'p1', ['f2','f1']);
  assert.equal(snapshot.raw, raw);
  assert.notEqual(JSON.stringify(JSON.parse(raw)), raw);
  assert.ok(snapshot.raw.includes('1792761234567890123'));
  assert.ok(snapshot.raw.includes('1792761234567890125'));
  assert.equal(snapshot.context.goal, 'Café "borrador"');
  assert.deepEqual(JSON.parse(request.body), {name:'atlas_context',arguments:{project_id:'p1',file_ids:['f2','f1']}});
  assert.equal(request.path, '/api/agent/call');
  assert.equal(request.credentials, 'same-origin');
  await assert.rejects(CC.referenceSnapshot(async()=>({ok:false,text:async()=>' {"ok":false,"error":"archivo no disponible"}'}),'p1',['f2']), /archivo no disponible/);
});

test('changedFields returns only edited fields', () => {
  assert.deepEqual(CC.changedFields({ a: 1, b: [1, 2], c: 'x' }, { a: 1, b: [1, 2], c: 'y', d: 'new' }), { c: 'y', d: 'new' });
  assert.deepEqual(CC.changedFields(undefined, { a: 1 }), { a: 1 });
});

test('project editor keeps dirty empty goal and rebases untouched concurrent fields', () => {
  const p={name:'Original',goal:'Old goal',owner:'writer',members:['writer','lumiere'],state:'active'};
  const draft=CC.projectDraft(p);
  CC.editProjectDraft(draft,'goal','');draft.requestId='old-request';
  CC.refreshProjectDraft(draft,{...p,name:'Changed by assistant',members:['writer','borges'],state:'archived'});
  assert.equal(draft.values.name,'Changed by assistant');assert.equal(draft.values.members,'borges');
  assert.equal(draft.values.state,'archived');assert.equal(draft.values.goal,'');
  assert.deepEqual(draft.patch,{goal:''});assert.equal(draft.requestId,'old-request');
  CC.editProjectDraft(draft,'members','LUMIERE, borges, lumiere');
  assert.deepEqual(draft.patch,{goal:'',members:['borges','lumiere','writer']});assert.equal(draft.requestId,null);
  CC.editProjectDraft(draft,'goal','Old goal');
  assert.deepEqual(draft.patch,{members:['borges','lumiere','writer']});
});

test('editorContext collects answers keyed by form and is undefined without forms', () => {
  const target = new EventTarget();
  assert.equal(CC.editorContext(target), undefined);
  target.addEventListener('atlas:context-request', e => e.detail.provide({ form: 'one', fields: { x: 1 } }));
  target.addEventListener('atlas:context-request', e => e.detail.provide({ form: 'two', fields: {} }));
  target.addEventListener('atlas:context-request', e => e.detail.provide('junk'));
  assert.deepEqual(Object.keys(CC.editorContext(target)), ['one', 'two']);
});

test('debounced coalesces a burst into one trailing run', () => {
  let pending = null, runs = 0;
  const timers = { set: fn => { pending = fn; return 1; }, clear: () => { pending = null; } };
  const schedule = CC.debounced(() => { runs += 1; }, 250, timers);
  schedule(); schedule();
  pending();
  assert.equal(runs, 1);
  assert.equal(pending !== null, true);
});

test('buildContext uses the project as case and lists files; no project means no objects', () => {
  const view = { project: { id: 'p1', name: 'Lanzamiento', sphere: 'work', owner: 'writer', goal: 'g', state: 'active', members: ['writer'], path: '/d/p1', shared_path: '/d/p1/shared' } };
  const ctx = CC.buildContext({ view, area: 'shared', files: [{ id: 'f1', title: 'a.png', relative_path: 'shared/a.png', app: 'writer', revision: 'sha256:1', state: 'available', exists: true, path: '/d/p1/shared/a.png' }] });
  assert.deepEqual(ctx.project, { external_project_id: 'p1', title: 'Lanzamiento' });
  assert.deepEqual(ctx.active_objects.map(o => [o.kind, o.object_id]), [['project', 'p1'], ['file', 'f1']]);
  assert.equal(ctx.view.page, 'project');
  const empty = CC.buildContext({ view: null, editor: { project_create: { form: 'project_create' } } });
  assert.deepEqual(empty.active_objects, []);
  assert.equal(empty.project, undefined);
  assert.equal(empty.view.page, 'home');
  assert.ok(empty.view.editor.project_create);
});

// ---- the shipping app.js against stubbed DOM and API ----
class Element {
  constructor(tag = 'div') { this.tag = tag; this.children = []; this.attributes = {}; this.dataset = {}; this.namespaceURI = 'svg'; this.hidden = false; this.value = ''; this.textContent = ''; this.values = {}; }
  append(...v) { this.children.push(...v); }
  replaceChildren(...v) { this.children = v; }
  setAttribute(k, v) { this.attributes[k] = v; }
  removeAttribute(k) { delete this.attributes[k]; }
  addEventListener(type, listener) { (this.listeners ||= {})[type]=listener; }
  fire(type) { return this.listeners?.[type]?.({preventDefault(){}}); }
  contains(element) { return this===element||this.children.some(child=>child.contains?.(element)); }
  focus() {}
  setSelectionRange() {}
}
function boot({ projects, handler }) {
  const elements = new Map();
  const document = {
    querySelector: s => { if (!elements.has(s)) elements.set(s, new Element()); return elements.get(s); },
    createElement: t => new Element(t), createElementNS: (ns, t) => new Element(t),
  };
  const window = new EventTarget();
  const calls = [];
  const fetch = async (path, options) => {
    if (path === '/api/status') return { ok: true, json: async () => ({ ok: true, root: '/disk', projects }) };
    const body = JSON.parse(options.body);
    calls.push(body.name);
    return handler(body);
  };
  class FormData { constructor(form) { this.form = form; } [Symbol.iterator]() { return Object.entries(this.form.values)[Symbol.iterator](); } }
  const context = vm.createContext({ document, window, fetch, FormData, CustomEvent, EventTarget, setTimeout, clearTimeout, console, crypto:{randomUUID} });
  vm.runInContext(fs.readFileSync('atlas_hoard/ui/copilot-context.js', 'utf8'), context);
  vm.runInContext(fs.readFileSync('atlas_hoard/ui/external-references.js', 'utf8'), context);
  vm.runInContext(fs.readFileSync('atlas_hoard/ui/app.js', 'utf8'), context);
  return { elements, window, calls, context, q: s => document.querySelector(s) };
}
const project = { id: 'p1', name: 'Lanzamiento', sphere: 'work', owner: 'writer', goal: 'g', state: 'active', members: ['writer'], path: '/d/p1', shared_path: '/d/p1/shared', hoard_paths: { writer: '/d/p1/hoards/writer' } };
const ok = result => ({ ok: true, json: async () => ({ ok: true, result }) });
const plain = x => JSON.parse(JSON.stringify(x));
const tick = () => new Promise(r => setTimeout(r, 20));

test('accepted registration refreshes the same project after a folder switch without replacing drafts', async () => {
  const p={...project,members:['writer','lumiere'],hoard_paths:{...project.hoard_paths,lumiere:'/d/p1/hoards/lumiere'}};
  const file={id:'new-file',title:'Título enviado',app:'writer',relative_path:'shared/new.txt',path:'/d/p1/shared/new.txt',exists:true};
  let files=[],release,reads=0;
  const app=boot({projects:[p],handler:body=>{
    if(body.name==='atlas_file_register')return new Promise(resolve=>{release=()=>resolve(ok({file}));});
    reads++;return ok({project:p,files});
  }});
  await tick();
  const walk=(el,predicate)=>predicate(el)?el:el.children.map(child=>walk(child,predicate)).find(Boolean);
  const panel=vm.runInContext('fileRegistrationPanel({project:activeProject})',app.context);
  const path=walk(panel,el=>el.name==='relative_path'),title=walk(panel,el=>el.name==='title');
  path.value='shared/new.txt';path.fire('input');title.value='Título enviado';title.fire('input');
  const pending=walk(panel,el=>el.tag==='form').fire('submit');
  await tick();
  title.value='Edición posterior';title.fire('input');
  vm.runInContext('area="lumiere";render({project:activeProject,files:[]})',app.context);
  vm.runInContext('atlasCopilotContext.editFileDraft(fileDrafts.get(JSON.stringify(["p1","lumiere"])),"title","Otro borrador")',app.context);
  files=[file];release();await pending;
  assert.equal(reads,2,'a confirmed registration must refresh native files even after moving to another folder');
  assert.equal(vm.runInContext('area',app.context),'lumiere');
  assert.equal(vm.runInContext('fileDrafts.get(JSON.stringify(["p1","lumiere"])).values.title',app.context),'Otro borrador');
  const shared=walk(app.q('#main'),el=>el.tag==='button'&&el.textContent==='Compartidos');
  shared.fire('click');
  assert.ok(walk(app.q('#main'),el=>el.tag==='strong'&&el.textContent==='Título enviado'),'returning to Shared uses the refreshed file list');
  assert.equal(vm.runInContext('fileDrafts.get(JSON.stringify(["p1","shared"])).values.title',app.context),'Edición posterior');
  assert.equal(vm.runInContext('fileDrafts.get(JSON.stringify(["p1","shared"])).receipt.id',app.context),'new-file');
});

test('reference selection survives filters and refresh, retries errors and rejects late snapshots', async () => {
  let release;
  const app=boot({projects:[project],handler:body=>body.name==='atlas_context'
    ?new Promise(resolve=>{release=resolve;})
    :ok({project,files:[{id:'f1',title:'Uno',path:'/disk/uno',exists:true},{id:'f2',title:'Dos',path:'/disk/dos',exists:true}]})});
  await tick();
  const panel=()=>vm.runInContext('referencePanel({project:activeProject,files:[{id:"f1",title:"Uno",path:"/disk/uno",exists:true},{id:"f2",title:"Dos",path:"/disk/dos",exists:true}]})',app.context);
  const walk=(el,predicate)=>predicate(el)?el:el.children.map(child=>walk(child,predicate)).find(Boolean);
  const control=(el,text)=>walk(el,child=>child.textContent===text);
  const add=(el,id)=>{const select=walk(el,child=>child.id==='context-file');select.value=id;select.fire('change');control(el,'Añadir a la selección').fire('click');};
  let element=panel();add(element,'f1');
  const stale=control(element,'Preparar JSON').fire('click');
  add(element,'f2');
  release({ok:true,text:async()=>' {"ok":true,"result":{"context":{"project_id":"p1","files":[]}}}'});
  await stale;
  assert.equal(vm.runInContext('referenceDrafts.get("p1").snapshot',app.context),null);
  vm.runInContext('area="writer"',app.context);element=panel();
  assert.match(walk(element,child=>child.className==='context-count').textContent,/2 de 20/);
  const failed=control(element,'Preparar JSON').fire('click');
  release({ok:false,text:async()=>' {"ok":false,"error":"Fallo ficticio; reintenta"}'});await failed;
  assert.ok(control(element,'Fallo ficticio; reintenta'));
  assert.deepEqual(plain(vm.runInContext('referenceDrafts.get("p1").ids',app.context)),['f1','f2']);
  const retry=control(element,'Preparar JSON').fire('click');
  vm.runInContext('invalidateReferences(); selected="otro"',app.context);
  release({ok:true,text:async()=>' {"ok":true,"result":{"context":{"project_id":"p1","files":[]}}}'});await retry;
  assert.equal(vm.runInContext('referenceDrafts.get("p1").snapshot',app.context),null);
  vm.runInContext('selected="p1"',app.context);
  await app.window.hoardCopilot.onTurnEnd();await new Promise(resolve=>setTimeout(resolve,320));
  assert.deepEqual(plain(vm.runInContext('referenceDrafts.get("p1").ids',app.context)),['f1','f2']);
});

test('context() reads the open project through the app API and includes unsaved forms', async () => {
  const app = boot({ projects: [project], handler: () => ok({ project, files: [{ id: 'f1', title: 'a.png', relative_path: 'shared/a.png', app: 'writer', revision: 'r', state: 'available', exists: true, path: '/d/p1/shared/a.png' }] }) });
  await tick();
  app.q('#create-panel').hidden = false;
  app.q('#create-form').values = { name: 'Nuevo', owner: 'faustus', members: '', sphere: 'personal', goal: '' };
  app.q('#file-panel').hidden = false;
  app.q('#relative-path').value = 'shared/b.png';
  vm.runInContext('atlasCopilotContext.editFileDraft(fileDrafts.get(JSON.stringify(["p1","shared"])),"relative_path","shared/b.png");atlasCopilotContext.editFileDraft(fileDrafts.get(JSON.stringify(["p1","shared"])),"title","Portada ñ")',app.context);
  const ctx = plain(await app.window.hoardCopilot.context());
  assert.equal(ctx.project.external_project_id, 'p1');
  assert.deepEqual(ctx.active_objects.map(o => o.object_id), ['p1', 'f1']);
  assert.deepEqual(ctx.view.editor.project_create.fields, { name: 'Nuevo' });
  assert.deepEqual(ctx.view.editor.file_register.fields, { relative_path: 'shared/b.png', title:'Portada ñ' });
});

test('context() never throws: fetch errors and unknown ids yield no object', async () => {
  const app = boot({ projects: [project], handler: () => ({ ok: false, json: async () => ({ ok: false, error: 'project not found' }) }) });
  await tick();
  const ctx = plain(await app.window.hoardCopilot.context());
  assert.deepEqual(ctx.active_objects, []);
  assert.equal(ctx.project, undefined);
});

test('turn end refreshes once for both triggers and keeps the half-typed file path', async () => {
  const app = boot({ projects: [project], handler: () => ok({ project, files: [] }) });
  await tick();
  const before = app.calls.length;
  app.q('#file-panel').hidden = false;
  app.q('#relative-path').value = 'shared/typed-by-hand.png';
  vm.runInContext('fileDrafts.get(JSON.stringify(["p1","shared"])).open=true;atlasCopilotContext.editFileDraft(fileDrafts.get(JSON.stringify(["p1","shared"])),"relative_path","shared/typed-by-hand.png");atlasCopilotContext.editFileDraft(fileDrafts.get(JSON.stringify(["p1","shared"])),"title","Título pendiente")',app.context);
  app.window.dispatchEvent(new Event('hoard:copilot-turn-end'));
  app.window.hoardCopilot.onTurnEnd();
  await new Promise(r => setTimeout(r, 400));
  assert.equal(app.calls.length - before, 1);
  assert.equal(app.q('#relative-path').value, 'shared/typed-by-hand.png');
  assert.deepEqual(plain(vm.runInContext('fileDrafts.get(JSON.stringify(["p1","shared"])).values',app.context)),{relative_path:'shared/typed-by-hand.png',title:'Título pendiente'});
});

test('context() keeps the folder it started with when the area changes while the project fetch is pending', async () => {
  let release = null, hold = false;
  const view = { project: { ...project, members: ['writer'] }, files: [
    { id: 'fs', title: 's.png', relative_path: 'shared/s.png', app: 'writer', revision: 'r', state: 'available', exists: true, path: '/d/p1/shared/s.png' },
    { id: 'fw', title: 'w.png', relative_path: 'hoards/writer/w.png', app: 'writer', revision: 'r', state: 'available', exists: true, path: '/d/p1/hoards/writer/w.png' },
  ] };
  const app = boot({ projects: [project], handler: () => (hold ? new Promise(r => { release = () => r(ok(view)); }) : ok(view)) });
  await tick();
  vm.runInContext('area = "writer";fileRegistrationPanel({project:activeProject});atlasCopilotContext.editFileDraft(fileDrafts.get(JSON.stringify(["p1","writer"])),"relative_path","hoards/writer/x")', app.context);
  app.q('#file-panel').hidden = false;
  app.q('#relative-path').value = 'hoards/writer/x';
  hold = true;
  const pending = app.window.hoardCopilot.context();
  await tick();
  vm.runInContext('area = "shared"', app.context);
  release();
  const ctx = plain(await pending);
  assert.equal(ctx.view.area, 'writer');
  assert.deepEqual(ctx.active_objects.map(o => o.object_id), ['p1', 'fw']);
  assert.equal(ctx.view.editor.file_register.area, 'writer');
});
