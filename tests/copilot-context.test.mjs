import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const CC = require('../atlas_hoard/ui/copilot-context.js');

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
  addEventListener() {}
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
  const context = vm.createContext({ document, window, fetch, FormData, CustomEvent, EventTarget, setTimeout, clearTimeout, console });
  vm.runInContext(fs.readFileSync('atlas_hoard/ui/copilot-context.js', 'utf8'), context);
  vm.runInContext(fs.readFileSync('atlas_hoard/ui/external-references.js', 'utf8'), context);
  vm.runInContext(fs.readFileSync('atlas_hoard/ui/app.js', 'utf8'), context);
  return { elements, window, calls, context, q: s => document.querySelector(s) };
}
const project = { id: 'p1', name: 'Lanzamiento', sphere: 'work', owner: 'writer', goal: 'g', state: 'active', members: ['writer'], path: '/d/p1', shared_path: '/d/p1/shared', hoard_paths: { writer: '/d/p1/hoards/writer' } };
const ok = result => ({ ok: true, json: async () => ({ ok: true, result }) });
const plain = x => JSON.parse(JSON.stringify(x));
const tick = () => new Promise(r => setTimeout(r, 20));

test('context() reads the open project through the app API and includes unsaved forms', async () => {
  const app = boot({ projects: [project], handler: () => ok({ project, files: [{ id: 'f1', title: 'a.png', relative_path: 'shared/a.png', app: 'writer', revision: 'r', state: 'available', exists: true, path: '/d/p1/shared/a.png' }] }) });
  await tick();
  app.q('#create-panel').hidden = false;
  app.q('#create-form').values = { name: 'Nuevo', owner: 'faustus', members: '', sphere: 'personal', goal: '' };
  app.q('#file-panel').hidden = false;
  app.q('#relative-path').value = 'shared/b.png';
  const ctx = plain(await app.window.hoardCopilot.context());
  assert.equal(ctx.project.external_project_id, 'p1');
  assert.deepEqual(ctx.active_objects.map(o => o.object_id), ['p1', 'f1']);
  assert.deepEqual(ctx.view.editor.project_create.fields, { name: 'Nuevo' });
  assert.deepEqual(ctx.view.editor.file_register.fields, { relative_path: 'shared/b.png' });
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
  app.window.dispatchEvent(new Event('hoard:copilot-turn-end'));
  app.window.hoardCopilot.onTurnEnd();
  await new Promise(r => setTimeout(r, 400));
  assert.equal(app.calls.length - before, 1);
  assert.equal(app.q('#relative-path').value, 'shared/typed-by-hand.png');
});

test('context() keeps the folder it started with when the area changes while the project fetch is pending', async () => {
  let release = null, hold = false;
  const view = { project: { ...project, members: ['writer'] }, files: [
    { id: 'fs', title: 's.png', relative_path: 'shared/s.png', app: 'writer', revision: 'r', state: 'available', exists: true, path: '/d/p1/shared/s.png' },
    { id: 'fw', title: 'w.png', relative_path: 'hoards/writer/w.png', app: 'writer', revision: 'r', state: 'available', exists: true, path: '/d/p1/hoards/writer/w.png' },
  ] };
  const app = boot({ projects: [project], handler: () => (hold ? new Promise(r => { release = () => r(ok(view)); }) : ok(view)) });
  await tick();
  vm.runInContext('area = "writer"', app.context);
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
