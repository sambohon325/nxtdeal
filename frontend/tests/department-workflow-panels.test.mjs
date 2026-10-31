import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const catalog=JSON.parse(fs.readFileSync(new URL('./fixtures/department-workflow-catalog.json',import.meta.url),'utf8'));
const modules={};
for(const name of ['Marketing','Inventory','Service','Finance','Support']){
 const scope={exports:{},require:id=>id==='next/dynamic'?{default:()=>()=>null}:id==='react/jsx-runtime'?{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})}:id.includes('/auth')?{getSession:()=>({role:'ADMIN'})}:new Proxy({},{get:(_,key)=>key})};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL(`../components/${name}WorkflowPanel.tsx`,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,scope);modules[name]=scope.exports;
}
for(const workflow of catalog){
 test(`${workflow.key}: each published section opens its workflow tool`,()=>{
  const prefix=workflow.key.split('.')[0];const moduleName=['administration','readiness'].includes(prefix)?'Support':prefix[0].toUpperCase()+prefix.slice(1);const mod=modules[moduleName];const map=mod[`${moduleName.toLowerCase()}WorkflowSteps`];
  assert.equal(workflow.tabs.length,5);
  for(const tab of workflow.tabs){assert.ok(map[workflow.key]?.[tab],`Missing ${tab}`);const tree=mod[`${moduleName}WorkflowPanel`]({workflowKey:workflow.key,tab,theme:'dark',onDraftOpenChange:()=>{},onSavingChange:()=>{}});assert.equal(tree.props.title,tab);assert.ok(tree.props.children,`${tab} must contain a working tool`);assert.ok(tree.props.description.length>20);}
 });
}
test('published unavailable-tab migration covers exactly120 sections',()=>assert.equal(catalog.reduce((n,w)=>n+w.tabs.length,0),120));
