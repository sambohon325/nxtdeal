import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const elements=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(elements)];
test('failed repair order load exposes retry and a way back',async()=>{
 const state=[null,false,false,'Order unavailable'];let cursor=0,closed=0,requests=0;
 const source=ts.transpileModule(fs.readFileSync(new URL('../components/RepairOrderWorkspaceBoard.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const scope={exports:{},require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;
  if(name==='react/jsx-runtime')return jsx;
  if(name==='react')return {useEffect:()=>{},useState:initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],v=>state[i]=v];}};
  if(name==='@/lib/repairOrders')return {getRoWorkspace:async()=>{requests++;throw Error('Still unavailable');}};
  return {};
 }};vm.runInNewContext(source,scope);
 const render=()=>{cursor=0;return elements(scope.exports.RoWorkspaceModal({theme:'dark',roId:'SYN',catalog:{},onClose:()=>closed++,onChanged:()=>{}}));};
 let tree=render();assert.ok(tree.some(e=>e.props?.role==='alert'));
 tree.find(e=>e.type==='button'&&e.props.children==='Try again').props.onClick();
 await new Promise(resolve=>setImmediate(resolve));tree=render();assert.equal(requests,1);assert.ok(tree.some(e=>e.props?.role==='alert'));
 tree.find(e=>e.type==='button'&&e.props.children==='Back to repair orders').props.onClick();assert.equal(closed,1);
});

test('failed concern saves keep the draft; confirmed saves clear it',async()=>{
 const fixture={vehicle:{},workflow_checklist:[],concerns:[],ro_stage:'Inspection'};
 const state=[fixture,false,false,null,'concerns','Fictional concern','When braking'];let cursor=0,fail=true,changed=0;
 const source=ts.transpileModule(fs.readFileSync(new URL('../components/RepairOrderWorkspaceBoard.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const scope={exports:{},require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;
  if(name==='react/jsx-runtime')return jsx;
  if(name==='react')return {useEffect:()=>{},useState:initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],v=>state[i]=v];}};
  if(name==='@/lib/repairOrders')return {getRoWorkspace:async()=>fixture,addConcern:async()=>{if(fail)throw Error('Save unavailable');return {};}};
  return {};
 }};vm.runInNewContext(source,scope);
 const render=()=>{cursor=0;return elements(scope.exports.RoWorkspaceModal({theme:'dark',roId:'SYN',catalog:{stages:[]},onClose:()=>{},onChanged:()=>changed++}));};
 await render().find(e=>e.type==='button'&&e.props.children==='Add').props.onClick();
 assert.equal(state[5],'Fictional concern');assert.equal(state[6],'When braking');assert.equal(changed,0);
 fail=false;await render().find(e=>e.type==='button'&&e.props.children==='Add').props.onClick();
 assert.equal(state[5],'');assert.equal(state[6],'');assert.equal(changed,1);
});

test('repair order close paths preserve drafts until explicit discard and block pending saves',()=>{
 const state=[null,false,false,'Unavailable'];let cursor=0,closed=0;
 const source=ts.transpileModule(fs.readFileSync(new URL('../components/RepairOrderWorkspaceBoard.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const scope={exports:{},require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;
  if(name==='react/jsx-runtime')return jsx;
  if(name==='react')return {useEffect:()=>{},useState:initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],v=>state[i]=v];}};
  return {};
 }};vm.runInNewContext(source,scope);
 const render=()=>{cursor=0;return elements(scope.exports.RoWorkspaceModal({theme:'dark',roId:'SYN',catalog:{},onClose:()=>closed++,onChanged:()=>{}}));};
 const click=(tree,label)=>tree.find(e=>e.type==='button'&&e.props.children===label).props.onClick();
 render();
 for(const slot of [5,6,7,9,12]){
  state[slot]='Fictional unsaved text';
  click(render(),'Back to repair orders');assert.equal(closed,0);
  click(render(),'Keep editing');assert.equal(state[slot],'Fictional unsaved text');
  render()[0].props.onClick();assert.equal(closed,0);
  assert.ok(render().some(e=>e.props.children==='Discard draft and close'));
  click(render(),'Keep editing');state[slot]='';
 }
 state[5]='Keep this'; state[2]=true;
 render()[0].props.onClick();assert.equal(closed,0);
 assert.equal(render().find(e=>e.props.children==='Back to repair orders').props.disabled,true);
 state[2]=false;render()[0].props.onClick();click(render(),'Discard draft and close');assert.equal(closed,1);
});

test('repair order dialog contains keyboard focus, restores its opener and protects drafts on Escape',()=>{
 const state=[null,false,false,'Unavailable', 'overview','Unsaved concern'];let cursor=0,closed=0,focused='',prevented=0;const effects=[];
 class Control {constructor(name){this.name=name;this.isConnected=true;}focus(){focused=this.name;}getClientRects(){return [1];}}
 const opener=new Control('opener'),first=new Control('first'),last=new Control('last'),dialogControl=new Control('dialog');
 const doc={activeElement:opener,getElementById:()=>dialogControl};
 const source=ts.transpileModule(fs.readFileSync(new URL('../components/RepairOrderWorkspaceBoard.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const scope={document:doc,HTMLElement:Control,exports:{},require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;
  if(name==='react/jsx-runtime')return jsx;
  if(name==='react')return {useEffect:fn=>effects.push(fn),useState:initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],v=>state[i]=v];}};
  return {};
 }};vm.runInNewContext(source,scope);
 const render=()=>{cursor=0;return elements(scope.exports.RoWorkspaceModal({theme:'dark',roId:'SYN',catalog:{},onClose:()=>closed++,onChanged:()=>{}}));};
 let tree=render();const dialog=tree.find(e=>e.props.role==='dialog');assert.equal(dialog.props['aria-modal'],'true');
 const cleanup=effects.find(fn=>fn.toString().includes("activeElement"))();assert.equal(focused,'dialog');
 const target={querySelectorAll:()=>[first,last]};
 const key=(key,shiftKey=false)=>dialog.props.onKeyDown({key,shiftKey,currentTarget:target,preventDefault:()=>prevented++,stopPropagation:()=>{}});
 doc.activeElement=last;key('Tab');assert.equal(focused,'first');
 doc.activeElement=first;key('Tab',true);assert.equal(focused,'last');assert.equal(prevented,2);
 key('Escape');assert.equal(closed,0);assert.ok(render().some(e=>e.props.children==='Keep editing'));
 cleanup();assert.equal(focused,'opener');
});


test('repair order reports core drafts and pending saves to its parent and names its return destination',()=>{
 const state=[null,false,false,null,'concerns','Fictional unsaved concern'];let cursor=0,dirty=false,saving=false;
 const source=ts.transpileModule(fs.readFileSync(new URL('../components/RepairOrderWorkspaceBoard.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const scope={exports:{},require:name=>name.endsWith('/WorkspaceUi')?workControls:(name==='react/jsx-runtime'?jsx:name==='react'?{useState:initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],v=>state[i]=v];},useEffect:fn=>{if(/onDraftOpenChange|onSavingChange/.test(fn.toString()))fn();}}:{})};
 vm.runInNewContext(source,scope);
 const render=()=>{cursor=0;return elements(scope.exports.RoWorkspaceModal({inline:true,returnLabel:'Back to warranty queue',theme:'dark',roId:'SYN',catalog:{},onClose:()=>{},onChanged:()=>{},onDraftOpenChange:v=>dirty=v,onSavingChange:v=>saving=v}));};
 assert.ok(render().some(e=>e.type==='button'&&e.props.children==='Back to warranty queue'));assert.equal(dirty,true);
 state[2]=true;render();assert.equal(saving,true);
 state[2]=false;state[5]='';render();assert.equal(dirty,false);assert.equal(saving,false);
});
