import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const nodes=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(nodes)];
for(const [name,folder,label] of [['SalesCrmWorkspace','sales','sales'],['MarketingWorkspace','marketing','marketing']])test(`${label} task picker respects access and task search can be cleared`,()=>{
 const state=[];let cursor=0;
 const code=ts.transpileModule(fs.readFileSync(new URL(`../components/${folder}/${name}.tsx`,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const scope={exports:{},require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;
  if(name==='@/lib/bdcNavigation'){const module={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../lib/bdcNavigation.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,module);return module.exports;}
  if(name==='react/jsx-runtime')return jsx;
  if(name==='react')return {useEffect:()=>{},useState:initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];}};
  if(name==='next/dynamic')return {default:()=> 'placeholder'};
  if(name==='@/components/EntityDashPanel')return {EntityDashPanel:'entity'};
  if(name.endsWith('.css'))return {default:{}};
  if(name==='@/lib/salesCrm')return {defaultFilters:{kind:'Lead',q:'',owner:'',stage:'',source:'',sort:'newest'},stageLabel:v=>v};
  return {};
 }};vm.runInNewContext(code,scope);
 const render=()=>{cursor=0;return nodes(scope.exports[name]({session:{employeeId:'SYN',role:'SALES'},items:[{key:'overview',label:'Overview'}],initialItem:folder==='marketing'?'integrations':'overview',onOpenEntity:()=>{},onSettings:()=>{}}));};
 let tree=render();const picker=tree.find(e=>e.type==='label'&&e.props.children?.[0]===`Go to a ${label} task`);
 assert.ok(picker);const options=nodes(picker).filter(e=>e.type==='option');assert.ok(options.length);assert.ok(!options.some(e=>['routing','automation','campaigns','prospects'].includes(e.props.value)));
 tree.find(e=>e.type==='input'&&e.props.placeholder==='Search tasks…').props.onChange({target:{value:'no-such-task'}});
 tree=render();assert.ok(!tree.some(e=>e.type==='button'&&e.props['aria-current']==='page'));
 tree.find(e=>e.type==='button'&&e.props.children==='Show all tasks').props.onClick();
 tree=render();assert.ok(tree.some(e=>e.type==='button'&&e.props['aria-current']==='page'));
 if(folder==='marketing') {
  state[8]='Fictional';state[9]=[{id:'SYN-C',name:'Fictional Customer',entity_type:'Customer'}];
  tree=render();tree.find(e=>e.type==='button'&&e.props.children?.[0]==='Fictional Customer').props.onClick();
  tree=render();assert.equal(tree.find(e=>e.type==='entity').props.entityId,'SYN-C');
  tree.find(e=>e.type==='entity').props.onClose();tree=render();
  assert.equal(tree.find(e=>e.type==='input'&&e.props['aria-label']==='Search marketing records').props.value,'Fictional');
  assert.ok(tree.some(e=>e.type==='button'&&e.props.children?.[0]==='Fictional Customer'));
 }
});

