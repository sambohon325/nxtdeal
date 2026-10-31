import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const flatten=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(flatten)];
function harness(file,name,modules={},seed={}) {
 const state={...seed};let cursor=0;const effects=[];
 const scope={exports:{},require:id=>id.endsWith('/WorkspaceUi')?workControls:(id==='react/jsx-runtime'?jsx:id==='react'?{useState:initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];},useMemo:fn=>fn(),useEffect:fn=>effects.push(fn)}:modules[id]||{})};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../components/'+file+'.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText+`\nexports.subject=${name};`,scope);
 return {effects,render:props=>{cursor=0;return scope.exports.subject(props);}};
}

for (const [tab,method,button,fields] of [
 ['offers','submitOffer','Submit Offer',{6:'VEH-MISSING',7:'Synthetic Buyer',8:'12000'}],
 ['funds','recordFundsCollected','Record Funds Collected',{9:'VEH-MISSING',10:'12000',11:'check'}],
]) test('wholesale '+tab+' preserves entered values after a rejected save',async()=>{
 const h=harness('WholesaleDeskBoard','WholesaleDeskBoard',{'@/lib/productTheme':{PRODUCT_ACCENT_COLORS:[]},'@/lib/wholesaleDesk':{[method]:async()=>{throw Error('Vehicle not found');}}},{0:tab,3:false,...fields});
 await flatten(h.render({theme:'light'})).find(e=>e.type==='button'&&e.props.children===button).props.onClick();
 const tree=flatten(h.render({theme:'light'}));
 for (const value of Object.values(fields)) assert.ok(tree.some(e=>e.type==='input'&&e.props.value===value));
 assert.ok(tree.some(e=>e.props.children==='Vehicle not found'));
});
test('creating a deal from a lead opens that exact worksheet and returns to the lead',()=>{
 let changed=0;const h=harness('ProspectsBoard','LeadRecordModal',{'@/components/DealDeskBoard':{NewDealModal:'NewDeal',DealDetailModal:'DealDetail'},'@/lib/auth':{getSession:()=>({employeeId:'QA',role:'ADMIN'})},'@/lib/leadRecord':{getLeadRecord:async()=>({lead:{attributes:{}}})}},{0:{lead:{attributes:{ConvertedCustomerID:'CUST-QA'}},next_best_action:{action:'Call',reason:'Review'},timeline:[],related_entities:[]},1:false,6:true});
 const props={theme:'dark',leadId:'LEAD-QA',inline:true,onChanged:()=>changed++,onClose(){}};
 const newDeal=flatten(h.render(props)).find(e=>e.type==='NewDeal');assert.ok(newDeal);
 newDeal.props.onCreated('DEAL-QA');const detail=h.render(props);
 assert.equal(detail.type,'DealDetail');assert.equal(detail.props.dealId,'DEAL-QA');assert.equal(detail.props.initialTab,'worksheet');assert.equal(detail.props.inline,true);assert.equal(changed,1);
 detail.props.onClose();assert.notEqual(h.render(props).type,'DealDetail');
});
test('failed individual task updates retain the task and expose a refresh action',async()=>{
 let refreshed=0;const h=harness('OperationsTasksBoard','TaskRow',{'./WorkspaceUi':{WorkButton:'button'},'@/lib/operationsTasks':{updateOperationsTask:async()=>{throw Error('private failure');}}});
 const props={theme:'dark',task:{id:'TASK-QA',status:'open',priority:'normal',task_type:'custom',detail:'Review',owner_bucket:'Unassigned'},selected:false,onToggleSelect(){},onChanged:()=>refreshed++};
 await flatten(h.render(props)).find(e=>e.type==='button'&&e.props.children==='Start').props.onClick();
 const tree=flatten(h.render(props));assert.ok(tree.some(e=>e.props.role==='alert'));assert.equal(refreshed,0);
 tree.find(e=>e.type==='button'&&e.props.children==='Refresh task').props.onClick();assert.equal(refreshed,1);
 assert.ok(tree.some(e=>e.type==='button'&&e.props.children==='Start'));
});
test('vehicle workspace publishes refreshed counts to its parent overview',async()=>{
 const board={Recon:[{vehicle_id:'VEH-QA'}]};let received;
 const h=harness('InventoryWorkspaceBoard','InventoryWorkspaceBoard',{'@/lib/vehicleLifecycle':{getLifecycleCatalog:async()=>({stages:['Recon']}),getLifecycleBoard:async()=>board}});
 h.render({theme:'dark',compact:true,onBoardUpdated:value=>received=value});h.effects[0]();await new Promise(resolve=>setImmediate(resolve));assert.equal(received,board);
});

test('starting figures require every builder section to be reviewed before advancing',()=>{
 const scope={exports:{},require:id=>id.endsWith('/WorkspaceUi')?workControls:(id==='react/jsx-runtime'?jsx:{})};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../components/lab/StartingFigures.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,scope);
 const ready=scope.exports.startingFiguresReady;
 const definitions={identity:{},inventory:{},team:{}};
 const plan={sections:{identity:{reviewed_hash:'reviewed'},inventory:{reviewed_hash:'reviewed'},team:{}}};
 assert.equal(ready(plan,definitions),false);
 plan.sections.team.reviewed_hash='reviewed';assert.equal(ready(plan,definitions),true);
 delete plan.sections.inventory;assert.equal(ready(plan,definitions),false);
 assert.equal(ready({...plan,model_definition:{currency:'USD'}},definitions),true);
});

for(const [file,component,client,method] of [
 ['OperationsSchedulingBoard','ReconTab','operationsScheduling','getReconSchedule'],
 ['OperationsSchedulingBoard','DeliveryTab','operationsScheduling','getDeliveryRiskBoard'],
 ['OperationsSchedulingBoard','TransportTab','operationsScheduling','getTransportSchedule'],
 ['DocumentWorkflowsBoard','ApprovalsTab','documentWorkflows','getPendingApprovals'],
 ['LotControlBoard','VehicleDetailModal','lotControl','getLotControlView'],
 ['PricingDeskBoard','VehicleDetailModal','pricingDesk','getPricingView'],
 ['PortfolioBoard','LoanDetailModal','loanServicing','getLoanDetail'],
 ['ServiceOverviewBoard','ServiceOverviewBoard','serviceOverview','getServiceMyDay'],
]) test(file+' '+component+' exposes failed loading and permits retry',async()=>{
 let attempts=0;
 const h=harness(file,component,{['@/lib/'+client]:{[method]:async()=>{attempts++;throw Error('Temporary test outage');}},'@/lib/repairOrders':{getRoCatalog:async()=>({})},'@/lib/productTheme':{PRODUCT_ACCENT_COLORS:[]}});
 const props={theme:'light',vehicleId:'QA',loanId:'QA',onClose(){},onChanged(){}};
 h.render(props);h.effects[0]();await new Promise(resolve=>setImmediate(resolve));
 const tree=flatten(h.render(props));assert.ok(tree.some(e=>e.props.role==='alert'));const retry=tree.find(e=>e.type==='button'&&e.props.children==='Try again');assert.ok(retry);
 retry.props.onClick();await new Promise(resolve=>setImmediate(resolve));assert.equal(attempts,2);
});

test('review finalization saves current notes before locking and uses returned record', async()=>{
 const calls=[]; const saved={id:'R1',status:'finalized',factual_summary:[],manager_notes:'Current notes',finalized_by:'QA'};
 const h=harness('CoachingPanel','CoachingPanel',{'@/lib/coaching':{updateReviewNotes:async(id,notes)=>{calls.push(['notes',id,notes]);},finalizeReview:async id=>{calls.push(['finalize',id]);return saved;},listPerformanceReviews:async()=>({reviews:[saved]})}},{0:'reviews',7:{id:'R1',status:'draft',factual_summary:[]},9:'Current notes'});
 await flatten(h.render({theme:'light'})).find(e=>e.type==='button'&&e.props.children==='Finalize').props.onClick();
 assert.deepEqual(calls,[['notes','R1','Current notes'],['finalize','R1']]);
 assert.ok(flatten(h.render({theme:'light'})).some(e=>e.type==='button'&&e.props.children==='Share With Employee'));
});
test('sharing a review displays server-recorded actor and date immediately',async()=>{
 const saved={id:'R1',status:'shared',factual_summary:[],shared_by:'Manager QA',shared_at:'2026-10-21T10:00:00Z'};
 const h=harness('CoachingPanel','CoachingPanel',{'@/lib/coaching':{shareReview:async()=>saved,listPerformanceReviews:async()=>({reviews:[saved]})}},{0:'reviews',7:{id:'R1',status:'finalized',factual_summary:[]}});
 await flatten(h.render({theme:'light'})).find(e=>e.type==='button'&&e.props.children==='Share With Employee').props.onClick();
 const text=JSON.stringify(h.render({theme:'light'}));assert.ok(text.includes('Manager QA'));assert.ok(text.includes('2026-10-21'));
});

test('service appointment changes refresh capacity and assignment suggestions',async()=>{
 let capacityCalls=0,suggestionCalls=0;
 const h=harness('ServiceAppointmentsBoard','ServiceAppointmentsBoard',{'@/lib/productTheme':{PRODUCT_ACCENT_COLORS:[]},'@/lib/appointments':{listAppointments:async()=>[]},'@/lib/appointmentScheduling':{getCapacityPlanning:async()=>{capacityCalls++;return null;},suggestAssignee:async()=>{suggestionCalls++;return null;}}},{7:true});
 const tree=flatten(h.render({theme:'light'}));const modal=tree.find(e=>typeof e.props.onCreated==='function');assert.ok(modal);modal.props.onCreated();await new Promise(resolve=>setImmediate(resolve));assert.equal(capacityCalls,1);assert.equal(suggestionCalls,1);
});

test('workspace includes the global customer conversation host for department quick actions',()=>{
 const source=fs.readFileSync(new URL('../components/CommandCenter.tsx',import.meta.url),'utf8');
 const ast=ts.createSourceFile('CommandCenter.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 let hosts=0;function visit(n){if(ts.isJsxSelfClosingElement(n)&&n.tagName.getText(ast)==='CommsWorkspaceMount')hosts++;ts.forEachChild(n,visit);}visit(ast);assert.equal(hosts,1);
});

test('task creation uses form submission, retains rejected input and disables edits while saving',async()=>{
 let rejectSave,calls=0;const h=harness('OperationsTasksBoard','NewTaskForm',{'./WorkspaceUi':{WorkButton:'button'},'@/lib/operationsTasks':{createOperationsTask:()=>{calls++;return new Promise((resolve,reject)=>rejectSave=reject);}}},{1:'Inspect synthetic vehicle'});
 const props={theme:'dark',catalog:{task_types:['custom'],priorities:['normal'],owner_buckets:['Unassigned']},onCreated(){assert.fail('Rejected task must not appear created');}};
 let tree=flatten(h.render(props));assert.equal(tree[0].type,'form');assert.equal(tree.find(e=>e.type==='button').props.type,'submit');
 tree[0].props.onSubmit({preventDefault(){}});tree=flatten(h.render(props));assert.ok(tree.filter(e=>e.type==='input'||e.type==='select'||e.type==='button').every(e=>e.props.disabled));
 tree[0].props.onSubmit({preventDefault(){}});assert.equal(calls,1);
 rejectSave(Error('Save unavailable'));await new Promise(resolve=>setImmediate(resolve));tree=flatten(h.render(props));assert.ok(tree.some(e=>e.type==='input'&&e.props.value==='Inspect synthetic vehicle'));assert.ok(tree.some(e=>e.props.role==='alert'));
});

test('shared action buttons preserve explicit submit behavior and default other actions to button',()=>{
 const h=harness('WorkspaceUi','WorkButton');let clicked=0;
 let button=h.render({children:'Open record',onClick:()=>clicked++});assert.equal(button.type,'button');assert.equal(button.props.type,'button');button.props.onClick();assert.equal(clicked,1);
 button=h.render({children:'Save',type:'submit',variant:'primary',disabled:true});assert.equal(button.props.type,'submit');assert.equal(button.props.disabled,true);assert.equal(button.props['data-work-variant'],'primary');
});
