import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
import {renderToStaticMarkup} from 'react-dom/server';
import {WorkField} from './work-field-loader.mjs';
const elements=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(elements)];
for(const file of ['AppointmentsBoard.tsx','ServiceAppointmentsBoard.tsx']) {
 function harness(api={},clipboard) {
  let cursor=0;const states=[];
  const source=ts.transpileModule(fs.readFileSync(new URL('../components/'+file,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText+'\nexports.TestRow=AppointmentRow;';
  const scope={exports:{},navigator:{clipboard},window:{location:{origin:'https://fixture.invalid'}},require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;
   if(name==='react')return {useState:initial=>{const i=cursor++;if(!(i in states))states[i]=initial;return [states[i],v=>states[i]=typeof v==='function'?v(states[i]):v];}};
   if(name==='react/jsx-runtime')return jsx;
   if(name==='./WorkField')return {WorkField};
   if(name==='@/lib/productTheme')return {PRODUCT_ACCENT_COLORS:{}};
   if(name==='@/lib/appointmentScheduling')return {generateCheckinLink:async()=>({path:'/checkin/fixture'}),sendAppointmentReminder:async()=>({}),...api};
   return {};
  }};
  vm.runInNewContext(source,scope);
  const render=()=>{cursor=0;return scope.exports.TestRow({theme:'dark',appt:{id:'fixture',status:'scheduled',scheduled_start:'2026-10-03T20:00:00Z',appointment_type:'other'},busy:false,onAdvance(){}});};
  return {html:()=>renderToStaticMarkup(render()),click:async text=>{const button=elements(render()).find(e=>e.type==='button'&&String(e.props.children).includes(text));assert.ok(button,text);await button.props.onClick();}};
 }
 test(file+': simulation is never presented as delivered',async()=>{
  const h=harness();await h.click('Remind');await h.click('Send (simulated)');
  assert.match(h.html(),/Simulation recorded/);assert.doesNotMatch(h.html(),/Reminder sent/);
 });
 test(file+': failures expose safe retry feedback',async()=>{
  const fail=async()=>{throw Error('sensitive backend detail');};
  const h=harness({sendAppointmentReminder:fail,generateCheckinLink:fail});
  await h.click('Remind');await h.click('Send (simulated)');assert.match(h.html(),/could not be recorded/);
  await h.click('Check-In Link');assert.match(h.html(),/could not be created/);assert.doesNotMatch(h.html(),/sensitive backend detail|Copied!/);
 });
 test(file+': clipboard rejection or absence does not claim copied',async()=>{
  for(const clipboard of [undefined,{writeText:async()=>{throw Error('denied');}}]) {
   const h=harness({},clipboard);await h.click('Check-In Link');await h.click('Copy');
   assert.match(h.html(),/copy it manually/);assert.doesNotMatch(h.html(),/Copied!/);
  }
 });
 test(file+': copied appears only after clipboard resolves and resets for replacement',async()=>{
  let resolve;const h=harness({}, {writeText:()=>new Promise(r=>resolve=r)});
  await h.click('Check-In Link');const pending=h.click('Copy');assert.doesNotMatch(h.html(),/Copied!/);
  resolve();await pending;assert.match(h.html(),/Copied!/);
  await h.click('Check-In Link');assert.doesNotMatch(h.html(),/Copied!/);
 });
}
