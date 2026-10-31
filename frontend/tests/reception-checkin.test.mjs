import {workControls} from './work-controls-stub.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const source = ts.transpileModule(fs.readFileSync(new URL('../components/apps/screens/ReceptionCheckin.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const elements = e => !e || typeof e !== 'object' ? [] : [e, ...[e.props?.children].flat(Infinity).flatMap(elements)];
function harness(save, listError = null) {
  const state = [], calls = [];
  let cursor = 0, asyncIndex = 0, reloads = 0;
  const hook = initial => {
    const i = cursor++;
    if (!(i in state)) state[i] = initial;
    return [state[i], value => { state[i] = value; }];
  };
  const scope = { exports: {}, require: name => {if(name.endsWith('/WorkspaceUi'))return workControls;
    if (name === 'react') return { useState: hook, useRef: v => hook({ current: v })[0] };
    if (name === 'react/jsx-runtime') return jsx;
    if (name === '@/lib/apps/registry') return { accentOf: () => ({}) };
    if (name === './kit') return {useAsync: () => ({loading:false, data:{}, error:listError,reload:()=>{reloads++;}})};
    if (name === '@/lib/upSystem') return { logUp: async input => { calls.push(input); return save(input); } };
    throw Error(name);
  } };
  vm.runInNewContext(source, scope);
  const render = () => { cursor = 0; asyncIndex = 0; return scope.exports.ReceptionCheckin({ app: {}, screen: {} }); };
  const fill = (label, value) => elements(render()).find(e => e.props?.['aria-label'] === label).props.onChange({ target: { value } });
  return { render, fill, calls, reloads:()=>reloads };
}
const event = { preventDefault() {} };

test('confirmed visitor clears fields, guards duplicates and reports assignment only', async()=>{
 let resolve;const h=harness(()=>new Promise(r=>{resolve=r;}));h.fill('Visitor name','Fixture');
 const submit=elements(h.render()).find(e=>e.type==='form').props.onSubmit;
 const pending=submit(event);await submit(event);assert.equal(h.calls.length,1);
 assert.ok(elements(h.render()).filter(e=>e.type==='input').every(e=>e.props.disabled));
 resolve({first_name:'Fixture',assigned_to_name:'Fixture Rep'});await pending;
 const tree=h.render();assert.match(JSON.stringify(tree),/assigned to Fixture Rep/);assert.doesNotMatch(JSON.stringify(tree),/notified/);
 assert.equal(elements(tree).find(e=>e.props?.['aria-label']==='Visitor name').props.value,'');assert.equal(h.reloads(),1);
});
test('failed subsequent visitor retains draft and clears previous success',async()=>{
 let count=0;const h=harness(async()=>{if(count++===0)return{first_name:'First fixture'};throw Error('private details');});
 h.fill('Visitor name','First fixture');await elements(h.render()).find(e=>e.type==='form').props.onSubmit(event);
 h.fill('Visitor name','Second fixture');h.fill('Phone (optional)','5550100');await elements(h.render()).find(e=>e.type==='form').props.onSubmit(event);
 const tree=h.render();assert.match(JSON.stringify(tree),/could not be confirmed/);assert.doesNotMatch(JSON.stringify(tree),/private details|First fixture/);
 assert.equal(elements(tree).find(e=>e.props?.['aria-label']==='Phone (optional)').props.value,'5550100');
});
test('rotation load failure supports retry',()=>{
 const h=harness(()=>{},'unavailable');const tree=h.render();assert.equal(tree.props.error,'unavailable');tree.props.onRetry();assert.equal(h.reloads(),1);
});
