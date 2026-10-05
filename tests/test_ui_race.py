"""Execute the shipping JS with out-of-order project responses (no browser)."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_project_switch_discards_old_responses_and_removes_stale_registration_controls():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for the UI race regression")
    root = Path(__file__).resolve().parents[1]
    script = r'''
const vm = require('node:vm'), fs = require('node:fs'), assert = require('node:assert/strict');
class Element {
  constructor(tag='div'){this.tag=tag;this.children=[];this.attributes={};this.dataset={};this.namespaceURI='svg';}
  append(...v){this.children.push(...v);}
  replaceChildren(...v){this.children=v;}
  setAttribute(k,v){this.attributes[k]=v;}
  removeAttribute(k){delete this.attributes[k];}
  addEventListener(){}
}
const elements=new Map(), pending=new Map();
const document={querySelector:s=>{if(!elements.has(s))elements.set(s,new Element());return elements.get(s);},
  createElement:t=>new Element(t),createElementNS:(ns,t)=>new Element(t)};
const context=vm.createContext({document,fetch:(path,options)=>{
  if(path==='/api/status')return new Promise(()=>{});
  const body=JSON.parse(options.body);
  return new Promise(resolve=>pending.set(body.arguments.project_id,resolve));
}});
vm.runInContext(fs.readFileSync('atlas_hoard/ui/app.js','utf8'),context);
function answer(id,name){pending.get(id)({ok:true,json:async()=>({ok:true,result:{
  project:{id,name,members:['writer'],owner:'writer',path:'/ssd/'+id,shared_path:'/ssd/'+id+'/shared',hoard_paths:{writer:'/ssd/'+id+'/hoards/writer'}},files:[]}})});}
function text(element){return [element.textContent||'',...element.children.map(text)].join(' ');}
(async()=>{
 const a=vm.runInContext("choose('a')",context);
 assert.match(text(elements.get('#main')),/Cargando/);
 assert.doesNotMatch(text(elements.get('#main')),/Registrar archivo/);
 const b=vm.runInContext("choose('b')",context);
 answer('b','Beta'); await b;
 assert.match(text(elements.get('#main')),/Beta/);
 answer('a','Alpha'); await a;
 assert.equal(vm.runInContext('selected',context),'b');
 assert.match(text(elements.get('#main')),/Beta/);
 assert.doesNotMatch(text(elements.get('#main')),/Alpha/);
 assert.equal(elements.get('#main').attributes['aria-busy'],undefined);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run([node, "-e", script], cwd=root, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
