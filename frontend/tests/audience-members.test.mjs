import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';import ts from 'typescript';import * as jsx from 'react/jsx-runtime';
const flat=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(flat)];
test('audience picker searches canonical contacts, persists membership and retains errors',async()=>{
 let cursor=0,changed=0,fail=false;const states=[],calls=[];
 const scope={Error,exports:{},require:n=>n.endsWith('/WorkspaceUi')?workControls:(n==='react/jsx-runtime'?jsx:n==='react'?{useState:initial=>{const i=cursor++;if(!(i in states))states[i]=initial;return[states[i],v=>states[i]=typeof v==='function'?v(states[i]):v];}}:n==='@/lib/salesCrm'?{crmRequest:async url=>{calls.push(url);return{records:url.includes('kind=Lead')?[{id:'L1',name:'Sam QA',email:'test@example.test'}]:[]}}}:{getList:async()=>({member_ids:[]}),addListMembers:async(id,ids)=>{if(fail)throw Error('Save failed');calls.push(['add',id,ids])},removeListMembers:async(id,ids)=>calls.push(['remove',id,ids])})};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../components/bdc/AudienceMembers.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,scope);
 const render=()=>{cursor=0;return flat(scope.exports.AudienceMembers({listId:'LIST1',onChanged:()=>changed++}));};
 render().find(e=>e.type==='input').props.onChange({target:{value:'Sam QA'}});
 render().find(e=>e.type==='form').props.onSubmit({preventDefault(){}});await new Promise(r=>setImmediate(r));
 assert.ok(calls[0].includes('q=Sam%20QA'));
 const member=()=>render().find(e=>e.type==='button'&&Array.isArray(e.props.children));
 await member().props.onClick();await new Promise(r=>setImmediate(r));assert.equal(changed,1);assert.equal(member().props.children[0],'Remove');
 await member().props.onClick();await new Promise(r=>setImmediate(r));assert.equal(changed,2);assert.equal(member().props.children[0],'Add');
 fail=true;await member().props.onClick();await new Promise(r=>setImmediate(r));assert.equal(changed,2);assert.ok(render().some(e=>e.props.children==='Save failed'));assert.equal(member().props.children[0],'Add');
});
