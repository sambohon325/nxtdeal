import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const elements=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(elements)];
function harness(seed,api={},component="PartsDeskBoard",props={}){
 const state=seed;let cursor=0;
 const source=ts.transpileModule(fs.readFileSync(new URL('../components/PartsDeskBoard.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const scope={exports:{},require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;
  if(name==='react/jsx-runtime')return jsx;
  if(name==='react')return {useEffect:()=>{},useState:initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],v=>state[i]=v];}};
  if(name==='@/lib/productTheme')return {PRODUCT_ACCENT_COLORS:['blue']};
  return api;
 }};vm.runInNewContext(source,scope);
 return ()=>{cursor=0;return elements(scope.exports[component]({theme:'dark',...props}));};
}
const queue={count:2,requests:[{id:'P1',ro_id:'R1',status:'requested',description:'Fictional brake pads',customer_name:'Avery Example',service_number:'SYN-1'},{id:'P2',ro_id:'R2',status:'ordered',description:'Fictional filter',vendor:'Demo Vendor',service_number:'SYN-2'}]};
test('parts worklist searches all requests, combines status and restores filters after record return',()=>{
 const state=[queue,null,null,{},false,null,'',null,null,'demo vendor'];const render=harness(state);
 let tree=render();assert.ok(tree.some(e=>e.props.children==='Fictional filter'));assert.ok(!tree.some(e=>e.props.children==='Fictional brake pads'));
 tree.find(e=>e.type==='button'&&e.props.className==='text-left min-w-0 min-h-11').props.onClick();assert.equal(state[8],'R2');
 state[8]=null;assert.equal(state[9],'demo vendor');
 render().find(e=>e.type==='select').props.onChange({target:{value:'requested'}});
 tree=render();assert.ok(tree.some(e=>e.type==='button'&&e.props.children==='Clear filters'));
 tree.find(e=>e.props.children==='Clear filters').props.onClick();tree=render();
 assert.ok(tree.some(e=>e.props.children==='Fictional brake pads'));assert.ok(tree.some(e=>e.props.children==='Fictional filter'));assert.equal(queue.count,2);
});
test('parts loading failure offers a retry and clears the stale error on recovery',async()=>{
 const state=[null,null,null,null,false,'Unavailable'];let requests=0;
 const render=harness(state,{getPartsRequestQueue:async()=>{requests++;return queue;},getSpecialOrders:async()=>({special_orders:[]}),getInventoryRecommendations:async()=>({recommendations:[],not_yet_tracked:{reorder_points:""}}),getRoCatalog:async()=>({})});
 render().find(e=>e.props.children==='Retry loading parts').props.onClick();
 await new Promise(resolve=>setImmediate(resolve));assert.equal(requests,1);assert.equal(state[5],null);assert.equal(state[0],queue);assert.ok(!render().some(e=>e.props.role==='alert'));
});


test('supplier order requires explicit confirmation and preserves failed entry for retry',async()=>{
 const state=['Demo Vendor','2026-10-20',false,false,null];let calls=0,done=0;
 const render=harness(state,{markSpecialOrder:async(ro,id,vendor,eta)=>{calls++;assert.equal(ro,'R1');assert.equal(id,'P1');assert.equal(vendor,'Demo Vendor');assert.equal(eta,'2026-10-20');if(calls===1)throw Error('Unavailable');}},'SpecialOrderWorkspace',{request:queue.requests[0],onClose:()=>{},onDone:()=>done++});
 const save=()=>render().find(e=>e.type==='button'&&e.props.children==='Save supplier order record');
 assert.equal(save().props.disabled,true);await save().props.onClick();assert.equal(calls,0);
 render().find(e=>e.type==='input'&&e.props.type==='checkbox').props.onChange({target:{checked:true}});
 assert.equal(save().props.disabled,false);await save().props.onClick();assert.equal(done,0);assert.equal(state[4],'Unavailable');assert.equal(state[0],'Demo Vendor');
 await save().props.onClick();assert.equal(done,1);assert.equal(calls,2);
});
