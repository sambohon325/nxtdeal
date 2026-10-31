import {workControls} from './work-controls-stub.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const adminScope={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../lib/administrationNavigation.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,adminScope);
const flatten = e => !e || typeof e !== 'object' ? [] : [e, ...[e.props?.children].flat(Infinity).flatMap(flatten)];
function harness(role='ADMIN', allowed=['workload','pipeline','service','finance']) {
 const state=[]; let cursor=0;
 const source=ts.transpileModule(fs.readFileSync(new URL('../components/CommandCenter.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const scope={exports:{},require:name=>{if(name==='@/lib/administrationNavigation')return adminScope.exports;if(name.endsWith('/WorkspaceUi'))return workControls;
  if(name==='@/lib/departmentWork'){const module={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../lib/departmentWork.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,module);return module.exports;}
  if(name==='./GlassAppearance') return {useGlassAppearance:()=>({theme:'dark',settings:{motion:true},style:{},background:'showroom'}),GlassBrand:'GlassBrand',GlassIcon:'GlassIcon',AppearanceDialog:'AppearanceDialog'};
  if(name==='@/lib/bdcNavigation'){const module={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../lib/bdcNavigation.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,module);return module.exports;}
  if(name==='@/components/extras/useEngagement')return {useEngagement:()=>false};
  if(name==='react/jsx-runtime') return jsx;
  if(name==='react') return {useEffect:()=>{},useRef:()=>({current:null}),useState:initial=>{const i=cursor++; if(!(i in state)) state[i]=initial; return [state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];}};
  if(name==='next/navigation')return {useRouter:()=>({push:()=>{},replace:()=>{}})};
  if(name==='@/lib/useMessaging')return {useMessaging:()=>({directory:[]})};
  if(name==='@/lib/workspaceTools')return {WorkspaceToolsContext:{Provider:'provider'}};
  if(name.endsWith('.css'))return {default:{}};
  return new Proxy({}, {get:(_,key)=>key});
 }};
 vm.runInNewContext(source,scope);
 const render=()=>{cursor=0;return flatten(scope.exports.CommandCenter({}));};
 render(); state[0]={employeeId:'SYN-ADMIN',role,allowedDashboards:allowed};
 state[15]=[{key:'overview',label:'Overview'},{key:'tasks',label:'Daily tasks'}];
 return {state,render};
}
test('workspace exposes catalog workflows in persistent navigation before opening a detail',()=>{
 const h=harness();const tree=h.render();
 assert.ok(tree.some(e=>e.props?.id==='workflow-navigation'));
 const nav=tree.find(e=>e.type==='WorkspaceNavigation'&&e.props.department==='Operations');
 assert.deepEqual(nav.props.items,h.state[15]);
 nav.props.onSelect('tasks');
 assert.equal(h.state[6].item,'tasks');
 assert.ok(h.render().some(e=>e.type==='MenuDashBody'&&e.props.initialTheme==='dark'));
});
test('department shortcuts retain role filtering and admin restriction',()=>{
 const h=harness('SERVICE',['service']);const nav=h.render().find(e=>e.type==='nav'&&e.props['aria-label']==='Departments');
 const buttons=flatten(nav).filter(e=>e.type==='button');
 assert.deepEqual(buttons.map(e=>e.props.title),['BDC Center','Inventory','Service','Dealer Lab']);
});
test('department change returns to current time and clears stale catalog',()=>{
 const h=harness();h.state[8]=30;
 h.render().find(e=>e.type==='button'&&e.props.title==='Sales').props.onClick();
 assert.equal(h.state[8],0);assert.equal(h.state[2],'Sales');assert.equal(h.state[15].length,0);
 const sales=h.render().find(e=>e.type==='SalesCrmWorkspace');assert.equal(sales.props.theme,'dark');
});
test('mobile workflow control exposes its navigation state',()=>{
 const h=harness();let tree=h.render();
 const toggle=tree.find(e=>e.type==='button'&&e.props.className?.includes('workflow-toggle'));
 assert.equal(toggle.props['aria-expanded'],false);toggle.props.onClick();
 tree=h.render();assert.equal(tree.find(e=>e.type==='button'&&e.props.className?.includes('workflow-toggle')).props['aria-expanded'],true);
});

test('Today returns each department to its own home and resets nested Sales/Marketing selection',()=>{
 for(const department of ['Sales','Marketing','Service','Finance','Inventory','Administration']){
  const h=harness();h.state[2]=department;h.state[6]={kind:'menu',department,item:'overview'};h.state[8]=30;
  const tree=h.render();tree.find(e=>e.type==='button'&&e.props['aria-label']==='Today').props.onClick();
  assert.equal(h.state[6].department,department);assert.equal(h.state[6].item,'overview');assert.equal(h.state[8],0);
  if(['Sales','Marketing'].includes(department)){
   const type=department==='Sales'?'SalesCrmWorkspace':'MarketingWorkspace';
   const first=h.render().find(e=>e.type===type).key;
   h.render().find(e=>e.type==='button'&&e.props['aria-label']==='Today').props.onClick();
   assert.notEqual(h.render().find(e=>e.type===type).key,first);
  }
 }
 const h=harness();h.state[6]={kind:'menu',department:'Operations',item:'tasks'};
 h.render().find(e=>e.type==='button'&&e.props['aria-label']==='Today').props.onClick();assert.equal(h.state[6],null);
});


test('campaign draft blocks department, Today and logo exits until explicit discard',()=>{
 for (const destination of ['Sales','Today','Return to overview']) {
  const h=harness();h.state[2]='Marketing';h.state[6]={kind:'menu',department:'Marketing',item:'overview'};
  h.render().find(e=>e.type==='MarketingWorkspace').props.onDraftOpenChange(true);
  const click=()=>h.render().find(e=>e.type==='button'&&(e.props.title===destination||e.props['aria-label']===destination)).props.onClick();
  const detail=h.state[6];const key=h.render().find(e=>e.type==='MarketingWorkspace').key;
  click();assert.equal(h.state[2],'Marketing');assert.equal(h.state[6],detail);
  assert.equal(h.render().find(e=>e.type==='MarketingWorkspace').key,key);
  h.render().find(e=>e.type==='button'&&e.props.children==='Keep editing campaign').props.onClick();
  assert.ok(!h.render().some(e=>e.props?.role==='alert'));
  click();h.render().find(e=>e.type==='button'&&e.props.children==='Discard campaign and continue').props.onClick();
  if(destination==='Sales')assert.equal(h.state[2],'Sales');
  else if(destination==='Today')assert.notEqual(h.render().find(e=>e.type==='MarketingWorkspace').key,key);
  else assert.equal(h.state[6],null);
 }
});

test('employee draft protects department and Today exits without a modal',()=>{
 const h=harness();h.state[2]='Administration';h.state[6]={kind:'menu',department:'Administration',item:'users'};
 h.render().find(e=>e.type==='MenuDashBody').props.onDraftOpenChange(true);
 h.render().find(e=>e.type==='button'&&e.props.title==='Sales').props.onClick();
 assert.equal(h.state[2],'Administration');
 h.render().find(e=>e.props.children==='Keep editing employee').props.onClick();
 assert.equal(h.state[6].item,'users');
 h.render().find(e=>e.props['aria-label']==='Today').props.onClick();
 h.render().find(e=>e.props.children==='Discard employee work and continue').props.onClick();
 assert.equal(h.state[6].item,'overview');assert.equal(h.state[2],'Administration');
});

test('active employee save blocks exit without offering to discard the request',()=>{
 const h=harness();h.state[2]='Administration';h.state[6]={kind:'menu',department:'Administration',item:'users'};
 h.render().find(e=>e.type==='MenuDashBody').props.onSavingChange(true);
 h.render().find(e=>e.type==='button'&&e.props.title==='Sales').props.onClick();
 const wait=h.render().find(e=>e.props.children==='Wait for save to finish');assert.equal(wait.props.disabled,true);
 wait.props.onClick();assert.equal(h.state[2],'Administration');
 h.render().find(e=>e.type==='MenuDashBody').props.onSavingChange(false);
 assert.ok(h.render().some(e=>e.props.children==='The save has finished. Review its result below before continuing.'));
 h.render().find(e=>e.type==='button'&&e.props.children==='Continue').props.onClick();assert.equal(h.state[2],'Sales');
});

test('pending campaign save blocks department exit until the result returns',()=>{
 const h=harness();h.state[2]='Marketing';h.state[6]={kind:'menu',department:'Marketing',item:'campaigns'};
 h.render().find(e=>e.type==='MarketingWorkspace').props.onSavingChange(true);
 h.render().find(e=>e.type==='button'&&e.props.title==='Sales').props.onClick();
 const wait=h.render().find(e=>e.props.children==='Wait for save to finish');assert.equal(wait.props.disabled,true);wait.props.onClick();assert.equal(h.state[2],'Marketing');
 h.render().find(e=>e.type==='MarketingWorkspace').props.onSavingChange(false);
 h.render().find(e=>e.type==='button'&&e.props.children==='Continue').props.onClick();assert.equal(h.state[2],'Sales');
});

test('listing work protects department exits and pending uploads cannot be discarded',()=>{
 const h=harness();h.state[2]='Inventory';h.state[6]={kind:'menu',department:'Inventory',item:'merchandising'};
 h.render().find(e=>e.type==='MenuDashBody').props.onDraftOpenChange(true);
 h.render().find(e=>e.type==='button'&&e.props.title==='Sales').props.onClick();assert.equal(h.state[2],'Inventory');
 h.render().find(e=>e.props.children==='Keep editing listing').props.onClick();assert.equal(h.state[6].item,'merchandising');
 h.render().find(e=>e.type==='MenuDashBody').props.onSavingChange(true);
 h.render().find(e=>e.type==='button'&&e.props.title==='Sales').props.onClick();
 const wait=h.render().find(e=>e.props.children==='Wait for save to finish');assert.equal(wait.props.disabled,true);wait.props.onClick();assert.equal(h.state[2],'Inventory');
 h.render().find(e=>e.type==='MenuDashBody').props.onSavingChange(false);
 h.render().find(e=>e.props.children==='Discard listing work and continue').props.onClick();assert.equal(h.state[2],'Sales');
});

test('warranty work protects department exits and pending saves cannot be discarded',()=>{
 const h=harness();h.state[2]='Service';h.state[6]={kind:'menu',department:'Service',item:'warranty'};
 h.render().find(e=>e.type==='MenuDashBody').props.onDraftOpenChange(true);
 h.render().find(e=>e.type==='button'&&e.props.title==='Sales').props.onClick();assert.equal(h.state[2],'Service');
 h.render().find(e=>e.props.children==='Keep editing service work').props.onClick();assert.equal(h.state[6].item,'warranty');
 h.render().find(e=>e.type==='MenuDashBody').props.onSavingChange(true);
 h.render().find(e=>e.type==='button'&&e.props.title==='Sales').props.onClick();
 const wait=h.render().find(e=>e.props.children==='Wait for save to finish');assert.equal(wait.props.disabled,true);wait.props.onClick();assert.equal(h.state[2],'Service');
 h.render().find(e=>e.type==='MenuDashBody').props.onSavingChange(false);
 h.render().find(e=>e.props.children==='Discard service work and continue').props.onClick();assert.equal(h.state[2],'Sales');
});


test('Dealer Lab replaces Admin in the top navigation and opens the embedded lab',()=>{
 const h=harness();const nav=h.render().find(e=>e.type==='nav'&&e.props['aria-label']==='Departments');
 const buttons=flatten(nav).filter(e=>e.type==='button');
 assert.ok(!buttons.some(e=>e.props.title==='Administration'));
 buttons.find(e=>e.props.title==='Dealer Lab').props.onClick();
 assert.equal(h.state[2],'Network');
 assert.ok(h.render().some(e=>e.type==='DealershipLab'));
 assert.ok(h.render().some(e=>e.type==='button'&&e.props.children==='Administration'));
});

test('Operations overview opens its focused daily snapshot',()=>{
 const h=harness();h.render().find(e=>e.type==='button'&&e.props.title==='Operations').props.onClick();
 assert.ok(h.render().some(e=>e.type==='OperationsDay'));
 assert.ok(!h.render().some(e=>e.type==='MenuDashBody'));
});


test('account destinations switch the workspace without depending on a route change',()=>{
 for(const [label,department] of [['Administration','Administration'],['Readiness','Readiness']]){
  const h=harness();h.state[2]='Sales';h.state[6]={kind:'menu',department:'Sales',item:'overview'};h.state[8]=30;
  let closed=false;
  h.render().find(e=>e.type==='button'&&e.props.children===label).props.onClick({currentTarget:{closest:()=>({removeAttribute:()=>{closed=true;}})}});
  assert.equal(h.state[2],department);assert.equal(h.state[6].item,'overview');assert.equal(h.state[8],0);assert.equal(closed,true);
 }
});

test('opening a record returns to the originating work instead of resetting the department',()=>{
 const h=harness();h.state[6]={kind:'menu',department:'Operations',item:'overview'};
 h.render().find(e=>e.type==='OperationsDay').props.onOpenEntity('DEAL-SYN');
 const record=h.render().find(e=>e.type==='EntityDashPanel');assert.equal(record.props.entityId,'DEAL-SYN');
 record.props.onClose();assert.deepEqual(h.state[6],{kind:'menu',department:'Operations',item:'overview'});
});


test("Dealer Lab has one department entry and no duplicate account action",()=>{const tree=harness().render();assert.ok(!tree.some(e=>e.type==="button"&&e.props.children==="Dealership lab"));assert.equal(tree.filter(e=>e.type==="button"&&e.props.title==="Dealer Lab").length,1);});
