import {workControls} from './work-controls-stub.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const source=ts.transpileModule(fs.readFileSync(new URL('../components/apps/screens/ReceptionAppointments.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const elements=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children,e.props?.meta].flat(Infinity).flatMap(elements)];
const tick=()=>new Promise(r=>setImmediate(r));
function harness(status,update,records){let state=[],cursor=0,reloads=0;const calls=[];const hook=v=>{const i=cursor++;if(!(i in state))state[i]=v;return[state[i],v=>{state[i]=v}]};
 const scope={exports:{},require:n=>{if(n.endsWith('/WorkspaceUi'))return workControls;
  if(n==='react')return{useState:hook,useRef:v=>hook({current:v})[0]};if(n==='react/jsx-runtime')return jsx;
  if(n==='@/lib/apps/registry')return{accentOf:()=>({})};
  if(n==='./kit')return{useAsync:()=>({data:records ?? [{id:'fixture',status,scheduled_start:new Date().toISOString(),appointment_type:'service',department:'Service'}],reload:()=>{reloads++}})};
  if(n==='@/lib/appointments')return{updateAppointmentStatus:async(...a)=>{calls.push(a);return update()}};throw Error(n);
 }};vm.runInNewContext(source,scope);const render=()=>{cursor=0;return scope.exports.ReceptionAppointments({app:{},screen:{}})};return{render,calls,reloads:()=>reloads};}
test('closed or already arrived appointments have no arrival action',()=>{
 for(const status of ['cancelled','no_show','completed','arrived']){const h=harness(status);assert.equal(elements(h.render()).filter(e=>e.type==='button'&&e.props['aria-label']?.startsWith('Mark ')).length,0)}
});

test('refresh remains available without actionable appointments and is disabled during arrival',async()=>{
 const empty=harness('completed',()=>{},[]);
 elements(empty.render()).find(e=>e.type==='button'&&e.props.children==='Refresh appointments').props.onClick();
 assert.equal(empty.reloads(),1);
 let done;const pending=harness('confirmed',()=>new Promise(r=>{done=r}));
 elements(pending.render()).find(e=>e.props?.['aria-label']?.startsWith('Mark ')).props.onClick();
 assert.equal(elements(pending.render()).find(e=>e.type==='button'&&e.props.children==='Refresh appointments').props.disabled,true);
 done({});await tick();
 assert.equal(elements(pending.render()).find(e=>e.type==='button'&&e.props.children==='Refresh appointments').props.disabled,false);
});
test('rapid repeated arrival submits once and refreshes after confirmation',async()=>{
 let done;const h=harness('confirmed',()=>new Promise(r=>{done=r}));const button=elements(h.render()).find(e=>e.type==='button'&&e.props['aria-label']?.startsWith('Mark '));button.props.onClick();button.props.onClick();assert.equal(h.calls.length,1);done({});await tick();assert.equal(h.reloads(),1);
});
test('rejected arrival exposes safe refresh and retains original status',async()=>{
 const h=harness('scheduled',async()=>{throw Error('private failure')});elements(h.render()).find(e=>e.type==='button'&&e.props['aria-label']?.startsWith('Mark ')).props.onClick();await tick();const tree=h.render();const alert=elements(tree).find(e=>e.props?.role==='alert');assert.match(JSON.stringify(alert.props.children),/could not be confirmed/);assert.doesNotMatch(JSON.stringify(tree),/private failure/);assert.equal(h.reloads(),0);elements(tree).find(e=>e.type==='button'&&e.props.children==='Refresh appointments').props.onClick();assert.equal(h.reloads(),1);
});

test('reception times honor offsets, show timezone and tolerate invalid legacy values',()=>{
 const scope={exports:{},require:n=>{if(n.endsWith('/WorkspaceUi'))return workControls;
  if(n==='react')return{};
  if(n==='react/jsx-runtime')return jsx;
  return{};
 }};
 vm.runInNewContext(source+'\nexports.formatFixture=fmtTime;',scope);
 const iso='2026-10-03T14:30:00Z';
 assert.equal(scope.exports.formatFixture(iso),new Date(iso).toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'}));
 assert.equal(scope.exports.formatFixture('invalid'),'Time unavailable');
 assert.equal(scope.exports.formatFixture('2026-10-03T09:30:00-05:00'),scope.exports.formatFixture(iso));
});

test('today follows device calendar boundaries and orders instants across offsets',()=>{
 const now=new Date();const day=new Date(now.getFullYear(),now.getMonth(),now.getDate());
 const early=new Date(day.getTime()+60000),late=new Date(day.getTime()+120000),previous=new Date(day.getTime()-1),next=new Date(now.getFullYear(),now.getMonth(),now.getDate()+1);
 const row=(id,time)=>({id,scheduled_start:time,appointment_type:id,department:'Service',status:'confirmed'});
 const h=harness('confirmed',()=>{},[row('late',late.toISOString()),row('next',next.toISOString()),row('bad','invalid'),row('early',early.toISOString()),row('previous',previous.toISOString())]);
 const tree=h.render();const rows=elements(tree).filter(e=>typeof e.props?.primary==='string');
 assert.deepEqual(rows.map(e=>e.props.primary),['early · Service','late · Service']);
 assert.match(JSON.stringify(tree),/Some appointments have invalid times/);
});
