import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const scope={exports:{}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../lib/administrationNavigation.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,scope);
const {adminDestinations,organizeAdministration,adminDailyKeys,retiredAdminWorkflows}=scope.exports;
test('every existing administration destination has an explicit owner and distinct purpose',()=>{
 const catalog=fs.readFileSync(new URL('../../backend/core/menu_catalog.py',import.meta.url),'utf8').split('    "Administration": [')[1].split('\n    ],')[0];
 const keys=[...catalog.matchAll(/"key": "([^"]+)"/g)].map(m=>m[1]);
 assert.deepEqual(Object.keys(adminDestinations).sort(),keys.sort());
 assert.equal(new Set(Object.values(adminDestinations).map(d=>d.label)).size,keys.length);
 assert.equal(adminDestinations.success_center.area,'system');
 assert.equal(adminDestinations.team_management.area,'dealership');
 assert.equal(adminDestinations.connect.area,'related');
 assert.equal(adminDestinations.digital_retail.area,'related');
});
test('navigation projection preserves permissions and original dispatch keys',()=>{
 const input=[{key:'users',label:'Users',description:'old'},{key:'future',label:'Future',description:'unchanged'}];
 const result=organizeAdministration(input);
 assert.deepEqual([...result.map(x=>x.key)],['users','future']);
 assert.equal(result[0].label,'Employee directory');assert.equal(result[1],input[1]);assert.equal(input[0].label,'Users');
});
test('legacy generic workflows resolve to working administrative tools',()=>{
 assert.equal(Object.keys(retiredAdminWorkflows).length,4);
 for(const key of [...adminDailyKeys,...Object.values(retiredAdminWorkflows)])assert.ok(adminDestinations[key]);
 assert.equal(retiredAdminWorkflows['administration.onboarding'],'team_management');
 assert.equal(retiredAdminWorkflows['administration.executive_approval'],'governance');
});


test('dealership admins see no empty system area and system admins retain it',async()=>{
 const jsx=await import('react/jsx-runtime');
 const {workControls}=await import('./work-controls-stub.mjs');
 const module={exports:{},require:name=>{
  if(name==='react/jsx-runtime')return jsx;
  if(name==='react')return {useState:value=>[value,()=>{}]};
  if(name==='@/lib/administrationNavigation')return scope.exports;
  if(name==='./CollectionPagination')return {CollectionPagination:'pagination',collectionPage:total=>({current:0,start:0,end:Math.min(total,8)})};
  if(name==='./WorkspaceUi')return workControls;
  if(name==='./WorkField')return {WorkField:'label'};
  if(name==='./DepartmentOverview')return {OverviewHeader:'header'};
  return {default:{}};
 }};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../components/AdministrationDay.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,module);
 const flatten=node=>!node||typeof node!=='object'?[]:Array.isArray(node)?node.flatMap(flatten):[node,...flatten(node.props?.children)];
 for(const system of [false,true]){
  const allowed=new Set(Object.entries(adminDestinations).filter(([,item])=>system||item.area!=='system').map(([key])=>key));
  const tree=flatten(module.exports.AdministrationDay({theme:'dark',allowed,onSelectItem:()=>{}}));
  const nav=tree.find(node=>node.props?.['aria-label']==='Administration areas');
  const buttons=flatten(nav).filter(node=>node.type==='button').map(node=>node.props.children);
  assert.equal(buttons.includes('System administration'),system);
  assert.ok(buttons.includes('Dealership administration'));
 }
});

test('system capability comes from whoami and ignores a forged stored flag',async()=>{
 const module={exports:{},fetch:async()=>({ok:true,json:async()=>({employee_id:'SYN',role:'ADMIN',must_change_password:false,allowed_dashboards:['sales']})}),require:name=>name==='@/lib/api'?{API_BASE:'http://localhost:8000'}:name==='./canonicalApiUrl'?{canonicalApiUrl:value=>value}:{}};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../lib/auth.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,module);
 const result=await module.exports.resolveStaffSession({token:'synthetic',employeeId:'SYN',role:'ADMIN',isSystemAdmin:true});
 assert.equal(result.session.isSystemAdmin,false);
});
