import {workControls} from './work-controls-stub.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const adminScope={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../lib/administrationNavigation.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,adminScope);
const scope={exports:{},require:()=>adminScope.exports};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../lib/workspaceNavigation.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,scope);
const {groupNavigation,navigationGroups}=scope.exports;
const catalog=fs.readFileSync(new URL('../../backend/core/menu_catalog.py',import.meta.url),'utf8');
for(const [department,definitions] of Object.entries(navigationGroups).filter(([department])=>department!=="BDC")) {
 test(`${department}: every catalog destination has a deliberate group and is preserved`,()=>{
  const section=catalog.split(`    "${department}": [`)[1]?.split('\n    ],')[0];
  assert.ok(section,department);
  const keys=[...section.matchAll(/"key": "([^"]+)"/g)].map(m=>m[1]);
  const mapped=Object.values(definitions).flatMap(v=>v.split(' '));
  for(const key of keys) assert.ok(mapped.includes(key),`${department}/${key} missing`);
  const items=keys.map(key=>({key,label:key}));
  const result=groupNavigation(department,items).flatMap(g=>g.items);
  assert.deepEqual([...result.map(i=>i.key)].sort(),[...keys].sort());
  assert.equal(new Set(result.map(i=>i.key)).size,keys.length);
  assert.ok(groupNavigation(department,items).length<=4);
 });
}
test('grouping never adds unauthorized tools and retains unknown catalog extensions',()=>{
 const input=[{key:'parts',label:'Parts'},{key:'new_tool',label:'New tool'}];
 const groups=groupNavigation('Service',input);
 assert.equal(groups.length,2);assert.equal(groups[1].label,'Other tools');
 assert.deepEqual([...groups.flatMap(g=>g.items)],input);
 assert.ok(!groups.flatMap(g=>g.items).some(i=>i.key==='warranty'));
});
import * as jsx from 'react/jsx-runtime';
function navigation(component,role,items,initialItem="overview",tree=false){
 const source=ts.transpileModule(fs.readFileSync(new URL(`../components/${component}.tsx`,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const scope={exports:{},require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;
  if(name==='@/lib/bdcNavigation'){const module={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../lib/bdcNavigation.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,module);return module.exports;}
  if(name==='react/jsx-runtime')return jsx;
  if(name==='react')return {useState:v=>[v,()=>{}],useEffect:()=>{}};
  if(name==='react-dom')return {createPortal:v=>v};
  if(name==='next/dynamic')return {default:()=> 'dynamic'};
  if(name.endsWith('.css'))return {default:{}};
  if(name.endsWith('WorkspaceNavigation'))return {WorkspaceNavigation:'grouped'};
  if(name.endsWith('salesCrm'))return {defaultFilters:{kind:'Lead'}};
  return new Proxy({},{get:(_,k)=>k});
 }};
 vm.runInNewContext(source,scope);
 const name=component.split('/').at(-1);
 const root=scope.exports[name]({navigationHost:{},session:{employeeId:'SYN',role},items,initialItem,onSettings:()=>{},onOpenEntity:()=>{}});
 const all=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(all)];
 return tree?all(root):all(root).find(e=>e.type==='grouped').props.items;
}
test('Sales groups retain gated CRM extensions and authorized routing',()=>{
 const items=[{key:'prospects',label:'Prospects'},{key:'customers',label:'Customers'},{key:'accessories',label:'Accessories'}];
 const staff=navigation('sales/SalesCrmWorkspace','SALES',items).map(i=>i.key);
 for(const key of ['prospects','contacts','segments','duplicates','accounts','pipeline','tasks','customers','accessories'])assert.ok(staff.includes(key),key);
 assert.ok(!staff.includes('deals'));assert.ok(!staff.includes('routing'));
 assert.ok(navigation('sales/SalesCrmWorkspace','ADMIN',items).some(i=>i.key==='routing'));
});
test('Marketing groups retain existing views and keep administrator tools gated',()=>{
 const items=[{key:'campaigns',label:'Campaigns'},{key:'crm',label:'CRM'},{key:'social_reputation',label:'Social'}];
 const staff=navigation('marketing/MarketingWorkspace','MARKETING',items).map(i=>i.key);
 for(const key of ['overview','planning','outreach','leads','campaigns','communications','social','reputation','agents','runs','content','integrations','settings'])assert.ok(staff.includes(key),key);
 assert.ok(!staff.includes('email'), 'Lifecycle planning requires the email workspace permission');
 assert.ok(!staff.includes('automation'));assert.ok(!staff.includes('native_workers'));assert.ok(!staff.includes('advertising'));
 const admin=navigation('marketing/MarketingWorkspace','ADMIN',items).map(i=>i.key);
 assert.ok(admin.includes('automation'));assert.ok(admin.includes('native_workers'));
});

const iconSource=ts.transpileModule(fs.readFileSync(new URL('../components/WorkspaceIcon.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const iconScope={exports:{},require:()=>jsx};vm.runInNewContext(iconSource,iconScope);
test('each department and each visible workflow group has a distinct purpose-built icon',()=>{
 const {WorkspaceIcon,workspaceIconPaths}=iconScope.exports;
 const path=name=>WorkspaceIcon({name}).props.children.props.d;
 const departments=Object.keys(navigationGroups);
 assert.equal(new Set(departments.map(path)).size,departments.length);
 for(const [department,definitions] of Object.entries(navigationGroups).filter(([department])=>department!=="BDC")) {
  const paths=[...Object.keys(definitions),'Guided workflows'].map(path);
  assert.equal(new Set(paths).size,paths.length,department);
  assert.ok(paths.every(p=>p!==workspaceIconPaths.other),department);
 }
 assert.equal(new Set(['vin','knowledge','help'].map(path)).size,3);
});
test('workspace keeps utilities accessible without adding a second messaging dock',()=>{
 const source=fs.readFileSync(new URL('../components/CommandCenter.tsx',import.meta.url),'utf8');
 assert.ok(!source.includes('useMessaging'));assert.ok(!source.includes('ChatDock'));
 assert.match(source, /<VinLookupWidget menuMode/);
 assert.match(source, /<HelpWorkspace /);
 assert.match(source, /<WelcomeTour /);
 assert.match(source, /href="\/apps" target="_blank" rel="noopener noreferrer"/);
});

 test('Service BDC uses its existing appointment workspace without exposing Sales tools',()=>{
 const items=[{key:'service:appointments',label:'Appointments'},{key:'sales:overview',label:'Overview'}];
 const service=navigation('bdc/BdcWorkspace','SERVICE',items).map(i=>i.key);
 assert.deepEqual(Array.from(service),['campaign_responses','service_appointments']);
 const admin=navigation('bdc/BdcWorkspace','ADMIN',items).map(i=>i.key);
 assert.ok(admin.includes('service_appointments'));assert.ok(admin.includes('today'));assert.ok(admin.includes('handoff'));
 });

test("Marketing Inventory opens its own workspace rather than the Paid media tab",()=>{const nodes=navigation("marketing/MarketingWorkspace","ADMIN",[{key:"inventory_advertising"},{key:"advertising"}],"inventory_advertising",true);assert.ok(nodes.some(n=>n.type==="OverviewHeader"&&n.props.title==="Inventory"));});
