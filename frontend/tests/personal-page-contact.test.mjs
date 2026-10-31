import {workControls} from './work-controls-stub.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const code=ts.transpileModule(fs.readFileSync(new URL('../components/PersonalPageContact.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const elements=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(elements)];
function harness(save){
 const state=[],calls=[];let cursor=0;
 const hook=initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],v=>state[i]=v];};
 const scope={exports:{},require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;
 if(name==='react')return{useState:hook,useRef:v=>hook({current:v})[0]};
 if(name==='react/jsx-runtime')return jsx;
 if(name==='@/lib/websites')return{publicSubmitPersonalSiteContactForm:async(...args)=>{calls.push(args);return save(...args)}};
 throw Error(name);
 }};vm.runInNewContext(code,scope);
 const render=()=>{cursor=0;return scope.exports.PersonalPageContact({slug:'fixture'});};
 const fill=(index,value)=>elements(render()).filter(e=>e.type==='input'||e.type==='textarea')[index].props.onChange({target:{value}});
 return{render,fill,calls};
}
const event={preventDefault(){}};
test('requires a trimmed name and contact method without calling API',async()=>{
 const h=harness(()=>{});h.fill(0,'  ');h.fill(1,'a@example.com');await h.render().props.onSubmit(event);assert.equal(h.calls.length,0);
 h.fill(0,'Visitor');h.fill(1,'');await h.render().props.onSubmit(event);assert.equal(h.calls.length,0);assert.match(JSON.stringify(h.render()),/Enter your name/);
});
test('duplicate click produces one request and confirmed receipt removes form',async()=>{
 let done;const h=harness(()=>new Promise(r=>done=r));h.fill(0,' Visitor ');h.fill(1,'a@example.com');
 const submit=h.render().props.onSubmit;const pending=submit(event);await submit(event);assert.equal(h.calls.length,1);assert.equal(h.calls[0][1].name,'Visitor');
 assert.ok(elements(h.render()).filter(e=>e.type==='input').every(e=>e.props.disabled));
 done({lead_id:'LEAD1'});await pending;assert.equal(h.render().props.role,'status');assert.match(JSON.stringify(h.render()),/request was received/);
});
test('network failure retains draft and never claims delivery',async()=>{
 const h=harness(async()=>{throw Error('private backend details');});h.fill(0,'Visitor');h.fill(2,'5550100');h.fill(3,'My question');await h.render().props.onSubmit(event);
 const tree=h.render();assert.match(JSON.stringify(tree),/couldn't confirm/);assert.doesNotMatch(JSON.stringify(tree),/private backend|request was received/);assert.equal(elements(tree).find(e=>e.type==='textarea').props.value,'My question');
});
test('malformed success is treated as unconfirmed',async()=>{
 const h=harness(async()=>({}));h.fill(0,'Visitor');h.fill(1,'a@example.com');await h.render().props.onSubmit(event);assert.match(JSON.stringify(h.render()),/couldn't confirm/);
});
