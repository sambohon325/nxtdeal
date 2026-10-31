import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const source = ts.transpileModule(fs.readFileSync(new URL('../components/SecurityReviewPanel.tsx', import.meta.url), 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS, jsx:ts.JsxEmit.ReactJSX}}).outputText;
function harness() {
  const states=[], effects=[], requests=[]; let cursor=0;
  const scope={exports:{}, AbortController, fetch:()=>new Promise((resolve,reject)=>requests.push({resolve,reject})), require:name=>name.endsWith('/WorkspaceUi')?workControls:(name==='react'?{
    useEffect:fn=>effects.push(fn), useState:initial=>{const i=cursor++;if(!(i in states))states[i]=initial;return [states[i],v=>{states[i]=typeof v==='function'?v(states[i]):v;}];}
  }:name==='react/jsx-runtime'?{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})}:name.includes('/auth')?{authHeaders:()=>({})}:{API_BASE:'https://example.invalid'})};
  vm.runInNewContext(source,scope);
  return {states,requests,render:()=>{cursor=0;effects.length=0;return scope.exports.SecurityReviewPanel();},start:()=>effects[0]()};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
const response=data=>({ok:true,json:async()=>data});
test('denied or unavailable evidence never renders a success report',async()=>{
  const h=harness();h.render();h.start();h.requests[0].resolve(response({error:'Access denied'}));await settle();
  assert.equal(h.states[1].report,undefined);assert.equal(h.states[1].error,'Access denied');
});
test('a stale request cannot repopulate reviewer information',async()=>{
  const h=harness();h.render();const cancel=h.start();cancel();h.requests[0].resolve(response({production_verified:false,mfa:{},verification_required:[]}));await settle();
  assert.equal(h.states[1],null);
});
test('unexpected certification response is rejected',async()=>{
  const h=harness();h.render();h.start();h.requests[0].resolve(response({production_verified:true,mfa:{},verification_required:[]}));await settle();
  assert.equal(h.states[1].report,undefined);assert.ok(h.states[1].error);
});
