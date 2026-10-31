import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';import ts from 'typescript';import * as jsx from 'react/jsx-runtime';
function component(file,name){const scope={exports:{},require:id=>id.endsWith('/WorkspaceUi')?workControls:(id==='react/jsx-runtime'?jsx:id==='react'?{useState:v=>[v,()=>{}],useEffect:()=>{}}:{})};vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL(`../components/${file}.tsx`,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText+`
exports.subject=${name};`,scope);return scope.exports.subject;}
for(const [file,name] of [['AppointmentsBoard','ScheduleModal'],['ProspectsBoard','LeadRecordModal'],['DealDeskBoard','NewDealModal'],['DealDeskBoard','DealDetailModal']])test(`${name} embeds inside the dashboard without a backdrop or click-away close`,()=>{
 const subject=component(file,name);const props={theme:'dark',leadId:'fictional',onClose:()=>{},onCreated:()=>{},onChanged:()=>{}};
 const inline=subject({...props,inline:true});assert.equal(inline.props.className,'workspace-inline-editor');assert.equal(inline.props.onClick,undefined);assert.match([inline.props.children].flat().find(child=>child?.type==="div").props.className,/workspace-editor-surface/);
 const legacy=subject(props);assert.match(legacy.props.className,/fixed inset-0/);assert.equal(legacy.props.onClick,props.onClose);
});

test('new deal retains the vehicle chosen in matching',()=>{
 const NewDeal=component('DealDeskBoard','NewDealModal');const root=NewDeal({theme:'dark',inline:true,initialVehicle:{id:'fictional-vehicle',year:2026,make:'Example',model:'Demo'},onClose:()=>{},onCreated:()=>{}});
 const walk=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(walk)];
 const nodes=walk(root);assert.ok(nodes.some(n=>n.type==='span'&&JSON.stringify(n.props.children).includes('Example')));
 assert.ok(!nodes.some(n=>n.type==='input'&&n.props.placeholder?.includes('Search inventory')));
});

test('Sales can read the Finance handoff without lender or approval actions',()=>{
 const Finance=component('DealDeskBoard','FinancingTab');const root=Finance({theme:'dark',deal:{id:'fictional-deal',status:'financing',financing_status:'not_started'},canDoFinancing:false,busy:false,act:()=>{throw Error('Unexpected mutation');}});
 const walk=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(walk)];const nodes=walk(root);
 assert.equal(nodes.filter(n=>n.type==='button').length,0);assert.ok(nodes.some(n=>n.type==='strong'&&n.props.children==='Finance handoff'));
});

test('contract preparation directs unfinished deals to their prerequisite without financial actions',()=>{
 const Contract=component('DealDeskBoard','ContractTab');const walk=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(walk)];
 for(const [status,financing_status,expected] of [['desking','not_started','worksheet'],['financing','declined','financing'],['financing','submitted','financing']]){
  let destination;const root=Contract({theme:'dark',deal:{id:'fictional',status,financing_status},canDoFinancing:true,onNavigate:tab=>destination=tab,act:()=>{throw Error('Unexpected mutation');}});
  const buttons=walk(root).filter(n=>n.type==='button');assert.equal(buttons.length,1);buttons[0].props.onClick();assert.equal(destination,expected);
 }
});
test('funding starts with inline review and cannot execute when the summary is missing',()=>{
 const Contract=component('DealDeskBoard','ContractTab');const walk=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(walk)];
 for(const contract of [null,{disclosures:[]}]){
  const nodes=walk(Contract({theme:'dark',deal:{status:'contract',contract},canDoFinancing:true,busy:false,act:()=>{throw Error('Unexpected mutation');}}));
  const buttons=nodes.filter(n=>n.type==='button');assert.equal(buttons.length,1);assert.equal(buttons[0].props.disabled,!contract);assert.match(buttons[0].props.children,/Review funding/);buttons[0].props.onClick();
 }
});
test('cancelled deals and Sales readers have no contract or funding mutations',()=>{
 const Contract=component('DealDeskBoard','ContractTab');const walk=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(walk)];
 for(const [status,canDoFinancing] of [['cancelled',true],['contract',false],['financing',false]]){
 const nodes=walk(Contract({theme:'dark',deal:{status,financing_status:'approved'},canDoFinancing,act:()=>{throw Error('Unexpected mutation');}}));assert.equal(nodes.filter(n=>n.type==='button').length,0);
 }
});
