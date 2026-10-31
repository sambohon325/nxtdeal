import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';import ts from 'typescript';import * as jsx from 'react/jsx-runtime';
const elements=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(elements)];

test('repair order inline mode avoids modal semantics and allows keyboard navigation back to the workspace',()=>{
 const source=ts.transpileModule(fs.readFileSync(new URL('../components/RepairOrderWorkspaceBoard.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const scope={exports:{},require:name=>name.endsWith('/WorkspaceUi')?workControls:(name==='react/jsx-runtime'?jsx:name==='react'?{useState:v=>[v,()=>{}],useEffect:()=>{}}:{})};vm.runInNewContext(source,scope);
 const root=scope.exports.RoWorkspaceModal({inline:true,theme:'dark',roId:'SYN',catalog:{},onClose:()=>{},onChanged:()=>{}});
 assert.equal(root.props.className,'workspace-inline-editor');assert.equal(root.props.onClick,undefined);const surface=elements(root).find(e=>e.props?.['aria-label']==='Repair order workspace');assert.equal(surface.props.role,'region');assert.equal(surface.props['aria-modal'],undefined);surface.props.onKeyDown({key:'Tab',preventDefault:()=>{throw Error('Inline Tab must not be trapped');}});
});


test('service intake is inline and preserves selected customer when Back is requested',()=>{
 const state=[];let cursor=0,closed=0;const source=ts.transpileModule(fs.readFileSync(new URL('../components/RepairOrderWorkspaceBoard.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const scope={exports:{},require:name=>name.endsWith('/WorkspaceUi')?workControls:(name==='react/jsx-runtime'?jsx:name==='react'?{useState:v=>{const i=cursor++;if(!(i in state))state[i]=v;return[state[i],x=>state[i]=x];},useEffect:()=>{}}:{})};vm.runInNewContext(source,scope);
 const render=()=>{cursor=0;return scope.exports.NewRoModal({inline:true,theme:'dark',onClose:()=>closed++,onCreated:()=>{}});};
 let root=render();assert.equal(root.props.className,'workspace-inline-editor');assert.equal(root.props.onClick,undefined);
 state[2]={id:'fictional',name:'Fictional Customer'};root=render();elements(root).find(e=>e.type==='button'&&e.props.children==='← Back to Service work').props.onClick();assert.equal(closed,0);
 root=render();assert.ok(elements(root).some(e=>e.props?.role==='alert'));elements(root).find(e=>e.type==='button'&&e.props.children==='Keep editing').props.onClick();assert.equal(state[2].id,'fictional');
});
