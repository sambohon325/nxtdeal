import {workControls} from './work-controls-stub.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
import { renderToStaticMarkup } from 'react-dom/server';

function harness(state, roster=async()=>[], component='ServiceTechs', sales=async()=>[], inspectionClient={}) {
 const source=ts.transpileModule(fs.readFileSync(new URL(`../components/apps/screens/${component}.tsx`,import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 let fetch, retries=0, slot=0;const states=[];
 const scope={exports:{},require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;
  if(name==='react/jsx-runtime')return jsx;
  if(name==='react')return {useRef:initial=>{const i=slot++;if(states[i]===undefined)states[i]={current:initial};return states[i];},useState:initial=>{const i=slot++;if(states[i]===undefined)states[i]=initial;return [states[i],v=>{states[i]=typeof v==='function'?v(states[i]):v;}];}};
  if(name==='@/lib/deals'||name==='@/lib/managerTo'||name==='@/lib/upSystem')return {};
  if(name==='@/lib/apps/registry')return {accentOf:()=>({})};
  if(name==='@/lib/vehicleInspection')return inspectionClient;
  if(name==='@/lib/repairOrders')return {getRoBoard:async()=>({})};
  if(name==='@/components/RepairOrderWorkspaceBoard')return {RoWorkspaceModal:()=>null};
  if(name==='@/lib/appointments')return {getServiceEmployees:roster};
  if(name==='@/lib/serviceOverview')return {};
  if(name==='@/lib/salesOverview')return {getSalesEmployees:sales};
  if(name==='@/components/apps/AppContactActions')return {AppContactActions:()=>null};
  if(name==='./kit')return {
   useAsync:fn=>{fetch=fn;return {...state,reload:()=>{retries++;}};},
   WiredScreen:({children})=>children,ListCard:({children})=>children,
   Row:({primary})=>primary,EmptyNote:({children})=>children,StatGrid:()=>null,Badge:({children})=>children,
  };
  throw Error(name);
 }};
 vm.runInNewContext(source,scope);
 return {render:()=>{slot=0;return scope.exports[component]({app:{},screen:{}});},request:()=>fetch(),retries:()=>retries};
}
test('all returned technician jobs remain visible beyond twelve',()=>{
 const ros=Array.from({length:15},(_,i)=>({id:`RO-${i}`,service_number:`JOB${i}`,description:`Fixture${i}`,technician:'TECH-1',ro_stage:'Repair'}));
 const h=harness({data:{board:{Repair:ros},roster:[{id:'TECH-1',name:'Fixture tech'}]}});
 const html=renderToStaticMarkup(h.render());
 for(let i=0;i<15;i++)assert.ok(html.includes(`Fixture${i}`), html);
});
test('roster failures propagate and the screen exposes retry',async()=>{
 const h=harness({error:'Unavailable'},async()=>{throw Error('Roster unavailable');});
 h.render().props.onRetry();assert.equal(h.retries(),1);
 await assert.rejects(h.request(),/Roster unavailable/);
});

const jobs=Array.from({length:15},(_,i)=>({id:`RO-${i}`,service_number:`JOB${i}`,description:`WorkItem${i}`}));
const leads=prefix=>Array.from({length:9},(_,i)=>({id:`${prefix}-${i}`,name:`${prefix}${i}`,overdue_task_count:1}));
test('reception directory reports either failed roster and supports retry',async()=>{
 for(const department of ['sales','service']) {
  const fail=async()=>{throw Error('Roster unavailable');};
  const h=harness({error:'Unavailable'},department==='service'?fail:undefined,'ReceptionDirectory',department==='sales'?fail:undefined);
  h.render().props.onRetry();assert.equal(h.retries(),1);
  await assert.rejects(h.request(),/Roster unavailable/);
 }
});
test('reception directory still deduplicates and sorts successful rosters',async()=>{
 const h=harness({},async()=>[{id:'shared',name:'Zoe',title:null},{id:'service',name:'Amy',title:null}],'ReceptionDirectory',async()=>[{id:'shared',name:'Zoe',title:null}]);
 h.render();const people=await h.request();
 assert.equal(people.length,2);assert.equal(people[0].name,'Amy');assert.equal(people[1].dept,'Sales');
});
for(const [component,data,expected] of [
 ['ServiceRoBoard',{Repair:jobs},jobs.map(x=>x.description)],
 ['ServiceManager',{advisor_dashboard:{advisor:{},my_appointments:{},my_waiting_customers:{},my_vehicles_ready:{},my_pending_approvals:{count:15,repair_orders:jobs}}},jobs.map(x=>x.description)],
 ['SalesToday',{my_tasks:{leads_requiring_contact_today:{count:9,items:leads('Contact')},missing_follow_ups:{count:9,items:leads('Overdue')},unsold_showroom_visits:{count:9,items:leads('Visitor')}}},['Contact8','Overdue8','Visitor8']],
]) {
 test(`${component} renders all returned work and provides retry`,()=>{
  const h=harness({data},undefined,component);
  const tree=h.render();const html=renderToStaticMarkup(tree);
  for(const item of expected)assert.ok(html.includes(item),item);
  const frame = component === 'ServiceRoBoard' ? tree.props.children[0] : tree;
  frame.props.onRetry();assert.equal(h.retries(),1);
 });
}



function inventoryHarness(summary, search, query='', component='InventoryScreen') {
 const source=ts.transpileModule(fs.readFileSync(new URL(`../components/apps/screens/${component}.tsx`,import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const states=[query,query,component==='VehicleShowroom'?60:30];let slot=0,request=0;const retries=[0,0];
 const scope={exports:{},require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;
  if(name==='react/jsx-runtime')return jsx;
  if(name==='react')return {useState:initial=>{const i=slot++;if(states[i]===undefined)states[i]=initial;return [states[i],v=>{states[i]=typeof v==='function'?v(states[i]):v;}];}};
  if(name==='@/lib/apps/registry')return {accentOf:()=>({bg:''})};
  if(name==='@/lib/inventoryWorkspace')return {normalizeListItem:v=>v,normalizeSearchHit:v=>v};
  if(name==='@/components/apps/VehicleCard')return {VehicleRow:({v})=>v.id,VehicleTile:({v})=>v.id};
  if(name==='@/components/DigitalRetailFlow')return {DigitalRetailFlow:()=>null};
  if(name==='./kit')return {
   useAsync:()=>{const i=request++;return {...[summary,search][i],reload:()=>retries[i]++};},
   WiredScreen:({children,error,loading,empty})=>error?'Unavailable':loading?'Loading':empty?'Unavailable':children,
   ListCard:({children})=>children,EmptyNote:({children})=>children,
  };
  throw Error(name);
 }};
 vm.runInNewContext(source,scope);
 return {render:()=>{slot=0;request=0;return scope.exports[component]({app:{},screen:{}});},retries};
}
const inventoryRows=Array.from({length:65},(_,i)=>({id:`UNIT-${i}-END`}));
const readyInventory={data:{vehicles:inventoryRows,count:65},loading:false,error:null};
const readySearch={data:{results:inventoryRows,count:65},loading:false,error:null};
function elements(tree,type) {
 if(!tree||typeof tree!=='object')return [];
 return [...((tree.type===type||tree.type?.name===type)?[tree]:[]),...[tree.props?.children].flat(Infinity).flatMap(child=>elements(child,type))];
}
test('inventory search failures are unavailable, never no matches; retry targets active request',()=>{
 const h=inventoryHarness(readyInventory,{error:'Network failure',loading:false,data:{results:[]}},'truck');
 const tree=h.render();assert.equal(renderToStaticMarkup(tree),'Unavailable');
 tree.props.onRetry();assert.deepEqual(h.retries,[0,1]);
 const lot=inventoryHarness({error:'Network failure',loading:false},readySearch);
 lot.render().props.onRetry();assert.deepEqual(lot.retries,[1,0]);
});
test('successful inventory searches remain usable if the background lot request failed',()=>{
 const h=inventoryHarness({error:'Network failure',loading:false},readySearch,'truck');
 assert.ok(renderToStaticMarkup(h.render()).includes('UNIT-0-END'));
});
for(const query of ['', 'truck'])test(`inventory show more reaches every returned vehicle (${query||'lot'}) and resets on search`,()=>{
 const h=inventoryHarness(readyInventory,readySearch,query);
 let tree=h.render();assert.ok(!renderToStaticMarkup(tree).includes('UNIT-30-END'));
 for(let i=0;i<2;i++) {
  elements(tree,'button').find(b=>String(b.props.children).includes('Show more vehicles')).props.onClick();
  tree=h.render();
 }
 assert.ok(renderToStaticMarkup(tree).includes('UNIT-64-END'));
 assert.ok(!elements(tree,'button').some(b=>String(b.props.children).includes('Show more vehicles')));
 elements(tree,'form')[0].props.onSubmit({preventDefault(){}});
 assert.ok(!renderToStaticMarkup(h.render()).includes('UNIT-30-END'));
});


test('sales customers exposes every merged customer, preserves bucket precedence and supports retry',()=>{
 const customers=Array.from({length:57},(_,i)=>({id:`C${i}`,name:`Customer-${i}-END`}));
 const data={my_tasks:{action_center:{items:customers.slice(0,20)},leads_requiring_contact_today:{items:[{id:'C0',name:'DuplicateWrong'},...customers.slice(20,40)]},missing_follow_ups:{items:customers.slice(40,50)},unsold_showroom_visits:{items:customers.slice(50)}}};
 const h=harness({data},undefined,'SalesCustomers');
 let tree=h.render();assert.ok(!renderToStaticMarkup(tree).includes('Customer-25-END'));
 for(let i=0;i<2;i++) {
  elements(tree,'button').find(b=>String(b.props.children).includes('Show more customers')).props.onClick();
  tree=h.render();
 }
 const html=renderToStaticMarkup(tree);
 for(const customer of customers)assert.ok(html.includes(customer.name),customer.name);
 assert.equal(html.split('Customer-0-END').length-1,1);
 assert.ok(!html.includes('DuplicateWrong'));
 assert.ok(!elements(tree,'button').some(b=>String(b.props.children).includes('Show more customers')));
 tree.props.onRetry();assert.equal(h.retries(),1);
});

test('sales customer search finds records beyond the initial page and recovers from no match',()=>{
 const customers=Array.from({length:40},(_,i)=>({id:`SYN-${i}`,name:`Fixture ${i}`,email:`fixture${i}@example.invalid`}));
 const h=harness({data:{my_tasks:{action_center:{items:customers}}}},undefined,'SalesCustomers');
 let tree=h.render();
 elements(tree,'input')[0].props.onChange({target:{value:' FIXTURE39@EXAMPLE.INVALID '}});
 let html=renderToStaticMarkup(h.render());assert.ok(html.includes('Fixture 39'));assert.ok(!html.includes('Fixture 0'));
 elements(h.render(),'input')[0].props.onChange({target:{value:'unmatched'}});
 tree=h.render();assert.ok(renderToStaticMarkup(tree).includes('No customers match'));
 elements(tree,'button').find(b=>b.props.children==='Show all customers').props.onClick();
 html=renderToStaticMarkup(h.render());assert.ok(html.includes('Fixture 0'));assert.ok(!html.includes('No customers match'));
});


test('inspection read failure cannot start an inspection; retry distinguishes confirmed not-started state',async()=>{
 let fail=true,started=0;
 const h=harness({data:{Inspection:[{id:'RO1',service_number:'101'}]}},undefined,'InspectionsScreen',undefined,{
  getInspection:async()=>{if(fail)throw Error('private provider detail');return {ro_id:'RO1',status:'not_started',summary:{},items:{}};},
  startInspection:async()=>{started++;return {ro_id:'RO1',status:'in_progress',summary:{},items:{}};},
 });
 let tree=h.render();const opening=elements(tree,'Row')[0].props.onClick();
 tree=h.render();assert.ok(renderToStaticMarkup(tree).includes('Loading inspection'));
 assert.ok(!renderToStaticMarkup(tree).includes('Start inspection'));
 await opening;tree=h.render();let html=renderToStaticMarkup(tree);
 assert.ok(html.includes('current status is unknown'));assert.ok(!html.includes('private provider detail'));assert.ok(!html.includes('Start inspection'));assert.equal(started,0);
 fail=false;await elements(tree,'button').find(b=>b.props.children==='Try again').props.onClick();
 tree=h.render();const start=elements(tree,'button').find(b=>String(b.props.children).includes('Start inspection'));
 assert.ok(start);await start.props.onClick();assert.equal(started,1);
 assert.ok(!renderToStaticMarkup(h.render()).includes('Start inspection'));
});

test('late inspection response cannot replace a newer repair order',async()=>{
 const pending={};
 const h=harness({data:{Inspection:[{id:'RO1',service_number:'101'},{id:'RO2',service_number:'102'}]}},undefined,'InspectionsScreen',undefined,{getInspection:id=>new Promise(resolve=>{pending[id]=resolve;})});
 let tree=h.render();const first=elements(tree,'Row')[0].props.onClick();tree=h.render();
 elements(tree,'button')[0].props.onClick();tree=h.render();const second=elements(tree,'Row')[1].props.onClick();
 pending.RO2({ro_id:'RO2',status:'completed',summary:{},items:{}});await second;
 pending.RO1({ro_id:'RO1',status:'not_started',summary:{},items:{}});await first;
 const finalTree=h.render();assert.equal(elements(finalTree,'Row')[0].props.meta.props.children,'completed');assert.ok(!renderToStaticMarkup(finalTree).includes('Start inspection'));
});


for(const [component,data,expected] of [
 ['DeskScreen',{deals:Array.from({length:23},(_,i)=>({id:`D${i}`,customer_id:`CustomerDesk${i}`,scenarios:[]})),tos:Array.from({length:13},(_,i)=>({id:`T${i}`,reason:`ManagerRequest${i}`}))},['CustomerDesk22','ManagerRequest12']],
 ['SalesUps',Array.from({length:23},(_,i)=>({id:`U${i}`,first_name:`Visitor${i}`,up_type:'walk_in',up_status:'working'})),['Visitor22']],
 ['InspectionsScreen',{Repair:jobs},['WorkItem14']],
])test(`${component} exposes returned work beyond former limits`,()=>{
 const h=harness({data},undefined,component);const tree=h.render();
 const html=renderToStaticMarkup(tree);for(const item of expected)assert.ok(html.includes(item),item);
 tree.props.onRetry();assert.ok(h.retries()>0);
});

test('showroom can browse beyond sixty vehicles and reset after a new search',()=>{
 const h=inventoryHarness(readyInventory,readySearch,'','VehicleShowroom');let tree=h.render();
 assert.ok(!renderToStaticMarkup(tree).includes('UNIT-64-END'));
 elements(tree,'button').find(b=>String(b.props.children).includes('Show more vehicles')).props.onClick();
 tree=h.render();assert.ok(renderToStaticMarkup(tree).includes('UNIT-64-END'));
 elements(tree,'form')[0].props.onSubmit({preventDefault(){}});
 assert.ok(!renderToStaticMarkup(h.render()).includes('UNIT-64-END'));
 const search=inventoryHarness({loading:true},readySearch,'truck','VehicleShowroom');
 assert.ok(renderToStaticMarkup(search.render()).includes('UNIT-0-END'));
});
