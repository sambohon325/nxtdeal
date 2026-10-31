import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const flatten=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(flatten)];
test('inline warranty claim retains failed work, blocks pending exits and confirms RO departure',async()=>{
 const state=[],refs=[];let c=0,r=0,calls=0,finish,closed=0,ro=null,dirty=false,saving=false;
 const scope={exports:{},require:n=>n.endsWith('/WorkspaceUi')?workControls:(n==='react/jsx-runtime'?jsx:n==='react'?{useEffect:fn=>fn(),useRef:i=>refs[r++]??(refs[r-1]={current:i}),useState:i=>{const k=c++;if(!(k in state))state[k]=i;return [state[k],v=>state[k]=v];}}:n.includes('productTheme')?{PRODUCT_ACCENT_COLORS:[]}:n.endsWith('warrantyDesk')?{submitWarrantyClaim:()=>{calls++;return new Promise((_,reject)=>finish=reject);}}:{})};
 const source=fs.readFileSync(new URL('../components/WarrantyDeskBoard.tsx',import.meta.url),'utf8').replace('function ClaimActionModal(', 'export function ClaimActionModal(');
 vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,scope);
 const render=()=>{c=r=0;return flatten(scope.exports.ClaimActionModal({theme:'dark',claim:{ro_id:'SYN-RO',service_number:'SYN-1',status:'draft'},onClose:()=>closed++,onDone:()=>closed++,onViewRo:id=>ro=id,onDraftOpenChange:v=>dirty=v,onSavingChange:v=>saving=v}));};
 assert.equal(render()[0].props.role,'region');assert.ok(!render()[0].props.className.includes('fixed'));
 render().find(e=>e.type==='input').props.onChange({target:{value:'SYN-OEM'}});
 render().find(e=>e.props.children==='View Full RO →').props.onClick();assert.equal(ro,null);assert.equal(dirty,true);
 render().find(e=>e.props.children==='Keep editing claim').props.onClick();
 const submit=render().find(e=>e.props.children==='Submit Claim').props.onClick;submit();submit();assert.equal(calls,1);
 assert.equal(render().find(e=>e.type==='fieldset').props.disabled,true);assert.equal(saving,true);
 render().find(e=>e.props.children==='Back to warranty queue').props.onClick();assert.equal(closed,0);
 finish(new Error('Fictional save failure'));await new Promise(resolve=>setImmediate(resolve));
 assert.equal(render().find(e=>e.type==='input').props.value,'SYN-OEM');assert.ok(render().some(e=>e.props.role==='alert'&&e.props.children==='Fictional save failure'));
 render().find(e=>e.props.children==='View Full RO →').props.onClick();render().find(e=>e.props.children==='Discard changes and continue').props.onClick();assert.equal(ro,'SYN-RO');
});

test('recall paging exposes every vehicle and retains the selected vehicle context',()=>{
 const state=[];let c=0,selected;
 const scope={exports:{},require:n=>n.endsWith('/WorkspaceUi')?workControls:(n==='react/jsx-runtime'?jsx:n==='react'?{useState:i=>{const k=c++;if(!(k in state))state[k]=i;return [state[k],v=>state[k]=v];}}:n.includes('productTheme')?{PRODUCT_ACCENT_COLORS:[]}:{}) };
 const source=fs.readFileSync(new URL('../components/WarrantyDeskBoard.tsx',import.meta.url),'utf8').replace('function RecallCampaignCard(', 'export function RecallCampaignCard(');
 vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,scope);
 const campaign={recall_id:'SYN-RECALL',recall_number:'SYN-001',completed:[],needs_repair:Array.from({length:52},(_,i)=>({vehicle_id:`SYN-${i}`,customer_name:`Fictional ${i}`,vin:`VIN-${i}`}))};
 const render=()=>{c=0;return flatten(scope.exports.RecallCampaignCard({theme:'light',campaign,onMarkComplete:(vehicle,recall)=>selected={vehicle,recall}}));};
 const button=label=>render().find(e=>e.type==='button'&&e.props.children===label);
 assert.equal(render().find(e=>e.props.label==='Recall vehicles').props.page,0);
 const seen=[];
 for(let page=0;page<3;page++){
  for(const action of render().filter(e=>e.type==='button'&&e.props.children==='Mark Completed')){action.props.onClick();seen.push(selected.vehicle.vehicle_id);assert.equal(selected.recall,campaign);}
  if(page<2)render().find(e=>e.props.label==='Recall vehicles').props.onPageChange(page+1);
 }
 assert.deepEqual(seen,campaign.needs_repair.map(v=>v.vehicle_id));
 assert.equal(render().find(e=>e.props.label==='Recall vehicles').props.page,2);
 campaign.needs_repair=campaign.needs_repair.slice(0,9);
 assert.equal(render().filter(e=>e.props.children==='Mark Completed').length,9);
 assert.equal(render().find(e=>e.props.label==='Recall vehicles').props.page,0);
});

test('recall completion retains failed RO entry and blocks duplicate submissions and departure',async()=>{
 const state=[],refs=[];let c=0,r=0,calls=0,rejectRequest,closed=0,dirty=false,saving=false,args;
 const scope={exports:{},require:n=>n.endsWith('/WorkspaceUi')?workControls:(n==='react/jsx-runtime'?jsx:n==='react'?{useEffect:fn=>fn(),useRef:i=>refs[r++]??(refs[r-1]={current:i}),useState:i=>{const k=c++;if(!(k in state))state[k]=i;return [state[k],v=>state[k]=v];}}:n.includes('productTheme')?{PRODUCT_ACCENT_COLORS:[]}:n.endsWith('warrantyDesk')?{markRecallCompleted:(...a)=>{args=a;calls++;return new Promise((_,reject)=>rejectRequest=reject);}}:{})};
 const source=fs.readFileSync(new URL('../components/WarrantyDeskBoard.tsx',import.meta.url),'utf8').replace('function MarkCompleteModal(', 'export function MarkCompleteModal(');
 vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,scope);
 const render=()=>{c=r=0;return flatten(scope.exports.MarkCompleteModal({theme:'light',vehicle:{vehicle_id:'SYN-V',vin:'SYN-VIN',customer_name:'Fictional customer'},campaign:{recall_id:'SYN-R',recall_number:'SYN-RECALL'},onClose:()=>closed++,onDone:()=>closed++,onDraftOpenChange:v=>dirty=v,onSavingChange:v=>saving=v}));};
 const button=name=>render().find(e=>e.type==='button'&&e.props.children===name);
 assert.equal(render()[0].props.role,'region');
 button('Mark Completed').props.onClick();assert.equal(calls,0);
 render().find(e=>e.type==='input').props.onChange({target:{value:' SYN-RO '}});
 button('Back to recall queue').props.onClick();assert.equal(closed,0);assert.equal(dirty,true);
 button('Keep editing recall').props.onClick();
 const submit=button('Mark Completed').props.onClick;submit();submit();assert.equal(calls,1);assert.equal(args.join(','),'SYN-V,SYN-R,SYN-RO');
 assert.equal(render().find(e=>e.type==='fieldset').props.disabled,true);assert.equal(saving,true);
 button('Back to recall queue').props.onClick();assert.equal(closed,0);
 rejectRequest(new Error('Fictional completion failed'));await new Promise(resolve=>setImmediate(resolve));
 assert.equal(render().find(e=>e.type==='input').props.value,' SYN-RO ');assert.equal(saving,false);
 assert.ok(render().some(e=>e.props.role==='alert'&&e.props.children==='Fictional completion failed'));
 button('Back to recall queue').props.onClick();button('Discard recall entry').props.onClick();assert.equal(closed,1);
});
