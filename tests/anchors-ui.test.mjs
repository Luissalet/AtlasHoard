import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

test('anchor panel builds selectors, lists statuses per revision and resolves a place', async () => {
  class Element {
    constructor(tag) {this.tag=tag;this.children=[];this.attributes={};this.dataset={};this.listeners={};this.hidden=false;this.value='';}
    append(...items) {this.children.push(...items);}
    replaceChildren(...items) {this.children=items;}
    setAttribute(k, v) {this.attributes[k]=String(v);}
    removeAttribute(k) {delete this.attributes[k];}
    addEventListener(name, fn) {this.listeners[name]=fn;}
    get lastChild() {return this.children[this.children.length-1];}
  }
  class Option extends Element {constructor(text, value) {super('option');this.textContent=text;this.value=value;}}
  const document = {createElement: tag => new Element(tag)};
  const walk = el => el.children.flatMap(c => [c, ...walk(c)]);
  const text = el => [el.textContent || '', ...el.children.map(text)].join(' ');
  const context = vm.createContext({document, Option, navigator: {language: 'es-ES'}});
  vm.runInContext(fs.readFileSync('atlas_hoard/ui/anchors.js', 'utf8'), context);
  const A = context.atlasAnchors;
  assert.deepEqual(JSON.parse(JSON.stringify(A.selectorFrom('pdf', {page: '2', x0: '0.1', y0: '0.2', x1: '0.5', y1: '0.4'}))), {page: 2, rect: [0.1, 0.2, 0.5, 0.4]});
  assert.deepEqual(JSON.parse(JSON.stringify(A.selectorFrom('cell', {ref: 'Hoja1!A1:B3'}))), {ref: 'Hoja1!A1:B3'});
  assert.deepEqual(JSON.parse(JSON.stringify(A.selectorFrom('text', {line_start: '4'}))), {line_start: 4, line_end: 4});
  assert.equal(A.place({kind: 'pdf', location: {page: 3, rect: [0, 0, 1, 1]}}), 'p.3 [0, 0, 1, 1]');
  const calls = [];
  const call = async (name, args) => {
    calls.push([name, args]);
    if (name === 'anchor_list') return {anchors: [{id: 'a1', uri: 'hoard://atlas/anchor/a1', label: 'Cláusula', kind: 'text', status: 'moved', revision_seq: 1, status_revision_seq: 2, detail: 'mismo texto', location: {line_start: 6, line_end: 6, quote: 'zorro'}}], revisions: [{seq: 1, revision: 'sha256:aaaaaaaaaaaa'}, {seq: 2, revision: 'sha256:bbbbbbbbbbbb'}]};
    if (name === 'anchor_resolve') return {open: {viewable: true, line_start: 6}, history: [{revision_seq: 1, status: 'intact', detail: 'x'}, {revision_seq: 2, status: 'moved', detail: 'y'}], comments: []};
    return {};
  };
  const view = {project: {id: 'p1', members: ['writer']}, files: [{id: 'f1', title: 'doc', relative_path: 'shared/doc.txt', exists: true}]};
  const panel = A.create({view, call, message() {}, copy() {}});
  const select = walk(panel).find(n => n.tag === 'select');
  select.value = 'f1';
  await select.listeners.change();
  const shown = text(panel);
  assert.match(shown, /Movida/);
  assert.match(shown, /Cláusula/);
  assert.match(shown, /r1 → r2/);
  assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1))), ['anchor_list', {file_id: 'f1'}]);
  const open = walk(panel).filter(n => n.tag === 'button').find(b => b.textContent === 'Abrir lugar');
  await open.listeners.click();
  assert.match(text(panel), /Se puede abrir en el archivo actual/);
  assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1))), ['anchor_resolve', {anchor_id: 'a1'}]);
});
