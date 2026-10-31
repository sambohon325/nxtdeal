import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';

const lifecycleScope={exports:{}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../components/lab/lifecycle.ts',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2017,module:ts.ModuleKind.CommonJS}}).outputText,lifecycleScope);
const lifecycle=lifecycleScope.exports;
const walk=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(walk)];
const plain=value=>JSON.parse(JSON.stringify(value));
function harness(file,exportName,dependencies={},globals={}){
 const cells=[],effects=[];let cursor=0;
 const memo=(fn,deps)=>{const i=cursor++,old=cells[i];if(!old||deps.some((v,j)=>v!==old.deps[j]))cells[i]={deps,value:fn()};return cells[i].value;};
 const react={useState:initial=>{const i=cursor++;if(!(i in cells))cells[i]=typeof initial==='function'?initial():initial;return [cells[i],value=>{cells[i]=typeof value==='function'?value(cells[i]):value;}];},useRef:initial=>memo(()=>({current:initial}),[]),useCallback:(fn,deps)=>memo(()=>fn,deps),useEffect:(fn,deps)=>{const i=cursor++,old=cells[i];if(!old||deps.some((v,j)=>v!==old.deps[j])){cells[i]={deps};effects.push(fn);}}};
 const scope={exports:{},structuredClone,crypto,console,Error,window:{confirm:()=>true,addEventListener(){},removeEventListener(){}},...globals,require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;if(name==='react')return react;if(name==='react/jsx-runtime')return jsx;if(name==='../RecordTable')return {RecordTable:'table'};if(name==='../CollectionPagination')return {CollectionPagination:'CollectionPagination'};if(name==='../DepartmentOverview')return {OverviewHeader:'OverviewHeader'};if(name.endsWith('.css'))return {default:new Proxy({},{get:(_,key)=>String(key)})};assert.ok(name in dependencies,'Unexpected dependency '+name);return dependencies[name];}};
 const code=ts.transpileModule(fs.readFileSync(new URL('../components/lab/'+file,import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2017,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 vm.runInNewContext(code,scope);
 return {scope,render(props){cursor=0;const tree=scope.exports[exportName](props);effects.splice(0).forEach(fn=>fn());return walk(tree);},async settle(){await new Promise(resolve=>setImmediate(resolve));}};
}

test('setup saves only configuration fields and preserves an unsaved source note',async()=>{
 const model={profile:{name:'Source dealership',country:'United States',region:'Texas',city:'Austin',currency:'USD'},dealership:{kind:'Independent',size:'small'},rooftops:1,workflow:{mode:'real',selected:true,setup_steps:[],calibration:[],review:null}};
 let savedPlan={id:'setup-plan',name:'Plan',revision:1,archived:false,model_definition:model};
 const calls=[],dirty=[];
 const request=async(path,method,body)=>{
  if(method==='POST'){
   calls.push(plain(body));
   savedPlan={...savedPlan,revision:2,model_definition:{...model,profile:{...model.profile,city:body.values.city}}};
   return savedPlan;
  }
  return {workspace:savedPlan,input:savedPlan.model_definition,modes:{real:'Real'},kinds:['Independent'],sizes:['small'],baseline_ready:false,source_summary:'Test source'};
 };
 const h=harness('LabSetup.tsx','LabSetup'),props={plan:savedPlan,request,onSaved:()=>{},onDirty:value=>dirty.push(value),onBusy:()=>{},onContinue:()=>{}};
 h.render(props);await h.settle();let nodes=h.render(props);
 nodes.find(n=>n.type==='input'&&n.props.value==='Austin').props.onChange({target:{value:'Dallas'}});
 nodes=h.render(props);
 nodes.find(n=>n.type==='textarea').props.onChange({target:{value:'Unsaved source period note'}});
 nodes=h.render(props);
 nodes.find(n=>n.type==='form').props.onSubmit({preventDefault(){}});
 await h.settle();nodes=h.render(props);
 assert.deepEqual(Object.keys(calls[0].values).sort(),['city','country','kind','region','reset_confirmed','rooftops','size']);
 assert.equal(calls[0].values.city,'Dallas');
 assert.equal(nodes.find(n=>n.type==='textarea').props.value,'Unsaved source period note');
 assert.equal(dirty.at(-1),true);
 assert.equal(nodes.find(n=>n.type==='button'&&n.props.children==='Continue to decisions →').props.disabled,true);
});
const WorkspaceNavigation=()=>null,StartingFigures=()=>null,DecisionChange=()=>null,LabAnalysis=()=>null;
const source={id:'base',name:'October assumptions',revision:3,parent_id:null,archived:false,updated_at:'2026-10-14',sections:{}};
const staffing={id:'staffing',title:'Change staffing',help:'Explicit assumptions',fields:[['role','Role',0,79,0],['people','People',0,500,1]]};
function workspace(){const portals=[];const h=harness('LabWorkspace.tsx','LabWorkspace',{
 './lifecycle':lifecycle,'react-dom':{createPortal:(node,host)=>{portals.push({node,host});return null;}},'../WorkspaceNavigation':{WorkspaceNavigation},'@/lib/api':{API_BASE:'http://fixture'},'@/lib/auth':{authHeaders:()=>({})},'./LabExperimentImport':{LabExperimentImport:()=>null},'./LabVersionHistory':{LabVersionHistory:()=>null},'./LabGoals':{LabGoals:()=>null},'./LabMix':{LabMix:()=>null},'./LabReferences':{LabReferences:()=>null},'./LabSoftware':{LabSoftware:()=>null},'./LabCampaigns':{LabCampaigns:()=>null},'./LabFinance':{LabFinance:()=>null},'./LabCustomers':{LabCustomers:()=>null},'./LabOperating':{LabOperating:()=>null},'./LabSetup':{LabSetup:()=>null},'./LabAnalysis':{LabAnalysis},'./StartingFigures':{StartingFigures},'./DecisionChange':{DecisionChange},'./LabNotebooks':{LabNotebooks:()=>null},'./LabPeriodReviews':{LabPeriodReviews:()=>null},'./LabReports':{LabReports:()=>null},
 },{fetch:async url=>({ok:true,json:async()=>String(url).endsWith('/decisions')?{decisions:[staffing]}:{workspaces:[source],sections:{}}})});return {...h,portals};}

test('Lab places its destinations in the existing sidebar host and carries the plan into comparison',async()=>{
 const h=workspace(),host={id:'existing-sidebar'},props={navigationHost:host};h.render(props);await h.settle();let nodes=h.render(props);
 assert.equal(h.portals.at(-1).host,host);
 assert.deepEqual(plain(h.portals.at(-1).node.props.items.map(i=>i.label)),['Setup & data sources','Departments & operating plan','Customers & inventory','Financial assumptions','Campaigns & demand','Customer & inventory mix','Public market references','Software planning','Explore a decision','Goal planner','Saved decisions','Starting figures','Monthly & quarterly reviews','Monthly reports','Success Workbooks','Procedure Bible']);
 assert.ok(!nodes.some(n=>n.type==='aside'));
 nodes.find(n=>n.type==='button'&&n.props.className==='decisionCard').props.onClick();nodes=h.render(props);
 const figures=nodes.find(n=>n.type===StartingFigures);assert.equal(figures.props.plan.id,'base');figures.props.onContinue();nodes=h.render(props);
 const change=nodes.find(n=>n.type===DecisionChange);assert.equal(change.props.plan.revision,3);
 await change.props.onCreated({...source,id:'option',name:'One more salesperson',parent_id:'base',revision:1});nodes=h.render(props);
 const compare=nodes.find(n=>n.type===LabAnalysis);assert.equal(compare.props.initialBaseline,'base');assert.equal(compare.props.initialProposed,'option');
 assert.equal(compare.props.plans.find(p=>p.id==='base').revision,3,'source is preserved');
});

test('Lab sidebar respects unsaved edits and blocks navigation during a save',async()=>{
 const h=workspace(),props={navigationHost:{}};h.render(props);await h.settle();let nodes=h.render(props);nodes.find(n=>n.type==='button'&&n.props.className==='decisionCard').props.onClick();nodes=h.render(props);
 nodes.find(n=>n.type===StartingFigures).props.onDirty(true);h.render(props);h.scope.window.confirm=()=>false;h.portals.at(-1).node.props.onSelect('saved');nodes=h.render(props);assert.ok(nodes.some(n=>n.type===StartingFigures));
 nodes.find(n=>n.type===StartingFigures).props.onDirty(false);nodes.find(n=>n.type===StartingFigures).props.onBusy(true);h.render(props);h.portals.at(-1).node.props.onSelect('saved');nodes=h.render(props);assert.ok(nodes.some(n=>n.type===StartingFigures));
 nodes.find(n=>n.type===StartingFigures).props.onBusy(false);h.render(props);h.portals.at(-1).node.props.onSelect('saved');nodes=h.render(props);assert.ok(nodes.some(n=>n.type===LabAnalysis&&n.props.historyOnly));
});

test('staffing uses the named sales role and total headcount, preserving revision and capacity warning',async()=>{
 const calls=[],created=[];const request=async(path,method,body)=>{calls.push({path,method,body});return method==='POST'?{id:'option'}:{input:{staffing_capacity_enabled:false,operating_enabled:true,scenario:{operating:{roles:[{id:'bdc',people:2,salary:4000,wage:0,shifts:1,scope:'rooftop'},{id:'sales',people:4,salary:6000,wage:0,shifts:1,scope:'rooftop'}]}}}};};
 const h=harness('DecisionChange.tsx','DecisionChange');const props={plan:source,template:staffing,request,onDirty(){},onBusy(){},onBack(){},onCreated:async p=>created.push(p)};h.render(props);await h.settle();const nodes=h.render(props);
 assert.ok(nodes.some(n=>typeof n.props.children==='string'&&n.props.children.includes('does not automatically increase sales capacity')));
 await nodes.find(n=>n.type==='form').props.onSubmit({preventDefault(){}});
 const write=calls.find(c=>c.method==='POST');assert.equal(write.path,'/workspaces/base/decisions');assert.deepEqual(plain(write.body.values),{role:1,people:5});assert.equal(write.body.revision,3);assert.equal(created[0].id,'option');
});

test('failed option save retains the change and exposes a retryable error',async()=>{
 const dirty=[],created=[];const request=async(path,method)=>{if(method==='POST')throw new Error('Revision changed. Reload before saving.');return {input:{staffing_capacity_enabled:false,scenario:{operating:{roles:[{id:'sales',people:4,salary:6000,wage:0,shifts:1,scope:'rooftop'}]}}}};};
 const h=harness('DecisionChange.tsx','DecisionChange'),props={plan:source,template:staffing,request,onDirty:v=>dirty.push(v),onBusy(){},onBack(){},onCreated:async p=>created.push(p)};h.render(props);await h.settle();let nodes=h.render(props);
 nodes.find(n=>n.type==='input'&&n.props.value===5).props.onChange({target:{value:'6'}});nodes=h.render(props);await nodes.find(n=>n.type==='form').props.onSubmit({preventDefault(){}});nodes=h.render(props);
 assert.ok(nodes.some(n=>n.props.role==='alert'&&n.props.children.includes('Revision changed')));assert.ok(nodes.some(n=>n.type==='input'&&n.props.value==='6'));assert.equal(created.length,0);assert.equal(dirty.at(-1),true);
});


test('operating editor preserves edits on failure and saves against the loaded revision',async()=>{
 const op={size:'small',open_days:26,open_hours:10,roles:[{id:'sales',name:'Sales',people:2,shifts:1,scope:'rooftop'}],tasks:[],expenses:[{name:'Rent',quantity:1,rate:1000,scope:'rooftop'}]};
 let saved={id:'op',name:'Synthetic dealership',revision:4,parent_id:null,archived:false,model_definition:{scenario:{operating:op},operating_enabled:true,staffing_capacity_enabled:false,profile:{currency:'USD'}}};
 let fail=true;const calls=[],dirty=[];
 const request=async(path,method,body)=>{if(method==='POST'){calls.push(plain(body));if(fail)throw Error('Revision conflict');saved={...saved,revision:5,model_definition:{...saved.model_definition,scenario:{operating:body.values.operating}}};return saved;}return {workspace:saved,input:saved.model_definition};};
 const h=harness('LabOperating.tsx','LabOperating',{'./departments':{departments:[['sales','Vehicle sales','Sales work',['Delivery']]],roleDepartments:{sales:'sales'}}});
 const props={plan:saved,request,onSaved:()=>{},onDirty:v=>dirty.push(v),onBusy:()=>{}};
 h.render(props);await h.settle();let nodes=h.render(props);
 for(const label of ['Building square feet','Lot square feet','Service bays','Detail bays','Parking spaces']){const field=nodes.find(n=>n.type==='label'&&n.props.children?.[0]===label);assert.equal(field.props.children[1].props.value,0,'unset optional facility descriptor must not block saves');}
 const rate=nodes.find(n=>n.type==='input'&&n.props.value===1000);rate.props.onChange({target:{value:'1700'}});
 nodes=h.render(props);nodes.find(n=>n.type==='form').props.onSubmit({preventDefault(){}});await h.settle();nodes=h.render(props);
 assert.equal(dirty.at(-1),true);assert.equal(nodes.find(n=>n.props?.role==='alert').props.children,'Revision conflict');assert.ok(nodes.some(n=>n.type==='input'&&n.props.value===1700));
 fail=false;nodes.find(n=>n.type==='form').props.onSubmit({preventDefault(){}});await h.settle();nodes=h.render(props);
 assert.equal(calls[1].revision,4);assert.equal(calls[1].action,'operating');assert.equal(calls[1].values.operating.expenses[0].rate,1700);assert.equal(dirty.at(-1),false);
 assert.equal(saved.revision,5);assert.equal(op.expenses[0].rate,1000,'loaded source was not mutated');
});

test('operating preview is read-only and disappears when draft inputs change',async()=>{
 const op={size:'small',open_days:26,open_hours:10,roles:[],tasks:[],expenses:[{name:'Rent',quantity:1,rate:1000,scope:'rooftop'}]};
 const plan={id:'preview',name:'Synthetic preview',revision:2,parent_id:null,archived:false,model_definition:{scenario:{operating:op},operating_enabled:true,staffing_capacity_enabled:false,profile:{currency:'USD'}}};
 const costs={payroll:0,additional_payroll:0,overhead:1000,cash_savings:0,operating_cost:1000,paid_hours:0,overload_hours:0};const calls=[];
 const request=async(path,method,body)=>{calls.push({path,method,body});return path.endsWith('/operating-preview')?{saved:costs,draft:costs,basis:'Illustrative',currency:'USD',rooftops:1,operating_enabled:true}:{workspace:plan,input:plan.model_definition};};
 const h=harness('LabOperating.tsx','LabOperating',{'./departments':{departments:[],roleDepartments:{}}});
 const props={plan,request,onSaved:()=>{throw Error('Preview must not save');},onDirty:()=>{},onBusy:()=>{}};
 h.render(props);await h.settle();let nodes=h.render(props);
 nodes.find(n=>n.type==='button'&&n.props.children==='Preview costs & workload').props.onClick({currentTarget:{form:{reportValidity:()=>true}}});await h.settle();nodes=h.render(props);
 assert.ok(nodes.some(n=>n.type==='table'));assert.equal(calls.at(-1).path,'/workspaces/preview/operating-preview');assert.equal(calls.at(-1).body.revision,2);
 nodes.find(n=>n.type==='input'&&n.props.value===1000).props.onChange({target:{value:'1200'}});nodes=h.render(props);
 assert.ok(!nodes.some(n=>n.type==='table'),'stale preview is hidden');assert.equal(op.expenses[0].rate,1000);
});

test('customer editor sends scoped assumptions and preserves draft after save failure',async()=>{
 const model={profile:{currency:'USD',organic_leads:200,new_share:0},segments:{new:{inventory:0},used:{inventory:20}},workflow:{calibration:[]}};
 let plan={id:'customers',name:'Synthetic plan',revision:3,parent_id:null,archived:false,model_definition:model};let fail=true;const calls=[],dirty=[];
 const request=async(path,method,body)=>{if(method==='POST'){calls.push(plain(body));if(fail)throw Error('Save interrupted');plan={...plan,revision:4,model_definition:{...model,profile:{...model.profile,...body.values.profile},segments:body.values.segments}};return plan;}return {workspace:plan,input:model,used_only:true,customer_fields:[['organic_leads','Organic leads',0,10000,1,'Demand'],['new_share','New share',0,100,.1,'Demand']],segment_fields:[['inventory','Stock',0,10000,1]]};};
 const h=harness('LabCustomers.tsx','LabCustomers'),props={plan,request,onSaved:()=>{},onDirty:v=>dirty.push(v),onBusy:()=>{}};
 h.render(props);await h.settle();let nodes=h.render(props);
 assert.equal(nodes.filter(n=>n.type==='input'&&n.props.disabled).length,2);
 assert.ok(nodes.some(n=>n.type==='input'&&n.props.step==='any'),'fractional assumptions retain source precision');
 nodes.find(n=>n.type==='input'&&n.props.value===200).props.onChange({target:{value:'300'}});nodes=h.render(props);
 nodes.find(n=>n.type==='form').props.onSubmit({preventDefault(){}});await h.settle();nodes=h.render(props);
 assert.equal(dirty.at(-1),true);assert.ok(nodes.some(n=>n.type==='input'&&n.props.value===300));
 fail=false;nodes.find(n=>n.type==='form').props.onSubmit({preventDefault(){}});await h.settle();h.render(props);
 assert.deepEqual(Object.keys(calls[1].values.profile).sort(),['new_share','organic_leads']);assert.equal(calls[1].revision,3);assert.equal(calls[1].action,'customers');assert.equal(dirty.at(-1),false);assert.equal(model.profile.organic_leads,200);
});

test('finance editor preserves whole-group fields and failed edits',async()=>{
 const model={profile:{currency:'CAD'},dealership:{kind:'Independent Used-Car Dealerships'},finance:{scenario:{opening_cash:10000,capex:500,apr:18}}};
 let plan={id:'finance',name:'Synthetic group',revision:7,parent_id:'source',archived:false,model_definition:model};let fail=true;const calls=[],dirty=[];
 const fields=[['opening_cash','Opening cash',-1e9,1e9,0,'Cash & earnings'],['capex','Capital spending',0,1e8,0,'Cash & earnings']];
 const request=async(path,method,body)=>{if(method==='POST'){calls.push(plain(body));if(fail)throw Error('Retry this save');plan={...plan,revision:8,model_definition:{...model,finance:{scenario:{...model.finance.scenario,...body.values.assumptions}}}};return plan;}return {workspace:plan,input:model,finance_fields:fields};};
 const h=harness('LabFinance.tsx','LabFinance'),props={plan,request,onSaved:()=>{},onDirty:v=>dirty.push(v),onBusy:()=>{}};
 h.render(props);await h.settle();let nodes=h.render(props);
 assert.equal(nodes.filter(n=>n.type==='input').length,2);
 nodes.find(n=>n.type==='input'&&n.props.value===500).props.onChange({target:{value:'2500.125'}});nodes=h.render(props);
 nodes.find(n=>n.type==='form').props.onSubmit({preventDefault(){}});await h.settle();nodes=h.render(props);assert.equal(dirty.at(-1),true);assert.ok(nodes.some(n=>n.type==='input'&&n.props.value===2500.125));
 fail=false;nodes.find(n=>n.type==='form').props.onSubmit({preventDefault(){}});await h.settle();h.render(props);
 assert.deepEqual(calls[1],{revision:7,action:'finance',values:{assumptions:{opening_cash:10000,capex:2500.125}}});assert.equal(dirty.at(-1),false);assert.equal(model.finance.scenario.capex,500);assert.equal(plan.model_definition.finance.scenario.apr,18);
});

test('campaign editor preserves legacy budget and permits explicit zero advertising',async()=>{
 const model={profile:{currency:'USD'},scenario:{spend:3000,cpl:60,saturation_budget:60000}};
 let plan={id:'campaigns',name:'Synthetic media',revision:2,parent_id:null,archived:false,model_definition:model};const calls=[];
 const request=async(path,method,body)=>{if(method==='POST'){calls.push(plain(body));plan={...plan,revision:3,model_definition:{...model,scenario:{...model.scenario,campaigns:[],spend:0,cpl:70}}};return plan;}return {workspace:plan,input:model};};
 const h=harness('LabCampaigns.tsx','LabCampaigns'),props={plan,request,onSaved:()=>{},onDirty:()=>{},onBusy:()=>{}};
 h.render(props);await h.settle();let nodes=h.render(props);
 assert.ok(nodes.some(n=>n.type==='input'&&n.props.value===3000));assert.ok(nodes.some(n=>n.type==='input'&&n.props.value==='Existing advertising budget'));
 nodes.find(n=>n.type==='button'&&n.props.children==='Remove campaign').props.onClick();nodes=h.render(props);nodes.find(n=>n.type==='form').props.onSubmit({preventDefault(){}});await h.settle();nodes=h.render(props);
 assert.deepEqual(calls[0],{revision:2,action:'campaigns',values:{campaigns:[],saturation_budget:60000}});assert.ok(!nodes.some(n=>n.type==='button'&&n.props.children==='Remove campaign'));assert.equal(model.scenario.spend,3000);
});

test('software estimates remain previews until added and manual edits retain source rationale',async()=>{
 const module={vendor:'test',name:'Synthetic software',rationale:'Archived analyst hypothesis',enabled:true,cost_scope:'group',estimate_case:'cautious',task_savings:{followup:10},monthly_cost:1000,setup_cost:200,adoption:75,integration:80,ramp_months:3,response_lift:2};
 const model={profile:{currency:'USD'},scenario:{software:[],operating:{tasks:[{id:'followup',name:'Follow-up'}]}}};const plan={id:'software',name:'Synthetic',revision:2,parent_id:null,archived:false,model_definition:model};const calls=[],dirty=[];
 const catalog={products:[{id:'custom',name:'Custom',description:'Custom'},{id:'test',name:'Synthetic software',description:'Test'}],templates:{custom:{...module,vendor:'custom'},test:module},effects:{response_lift:'Response %'},version:'test',checked:'2026-09-14'};
 const request=async(path,method,body)=>{calls.push({path,method,body:body&&plain(body)});if(path==='/software-catalog')return catalog;if(path==='/software-estimate')return module;if(method==='POST')return {...plan,revision:3,model_definition:{...model,scenario:{...model.scenario,software:body.values.modules}}};return {workspace:plan,input:model};};
 const h=harness('LabSoftware.tsx','LabSoftware'),props={plan,request,onSaved:()=>{},onDirty:v=>dirty.push(v),onBusy:()=>{}};
 h.render(props);await h.settle();let nodes=h.render(props);
 nodes.find(n=>n.type==='select'&&n.props.value==='custom').props.onChange({target:{value:'test'}});nodes=h.render(props);
 nodes.find(n=>n.type==='button'&&n.props.children==='Preview shared estimate').props.onClick();await h.settle();nodes=h.render(props);
 assert.equal(dirty.at(-1),false);assert.ok(!calls.some(c=>c.body?.action==='software'));
 nodes.find(n=>n.type==='button'&&n.props.children==='Add this estimate to draft').props.onClick();nodes=h.render(props);
 assert.equal(dirty.at(-1),true);nodes.find(n=>n.type==='input'&&n.props.value===1000).props.onChange({target:{value:'1200'}});nodes=h.render(props);
 nodes.find(n=>n.type==='form').props.onSubmit({preventDefault(){}});await h.settle();h.render(props);
 const saved=calls.find(c=>c.body?.action==='software').body;assert.equal(saved.revision,2);assert.equal(saved.values.modules[0].estimate_case,'manual');assert.equal(saved.values.modules[0].rationale,module.rationale);assert.equal(saved.values.modules[0].monthly_cost,1200);assert.equal(model.scenario.software.length,0);
});


test('historical recovery preserves retry identity and opens a separate copy',async()=>{
 const calls=[],created=[];let fail=true,ids=0;
 const version={...source,id:'version-2',revision:2};
 const request=async(path,method,body)=>{if(!method)return {versions:[version]};calls.push({path,body:plain(body)});if(fail)throw Error('Temporary response failure');return {...source,id:'recovered',name:body.name,revision:1};};
 const h=harness('LabVersionHistory.tsx','LabVersionHistory',{}, {crypto:{randomUUID:()=>`recovery-request-${++ids}`}}),props={plan:source,request,onCreated:v=>created.push(v),onBusy:()=>{},busy:false};
 let nodes=h.render(props);await nodes.find(n=>n.type==='button').props.onClick();nodes=h.render(props);
 nodes.find(n=>n.type==='select').props.onChange({target:{value:version.id}});nodes=h.render(props);
 await nodes.find(n=>n.type==='button'&&n.props.children==='Create separate copy').props.onClick();nodes=h.render(props);
 assert.ok(nodes.some(n=>n.props?.role==='alert'));assert.equal(created.length,0);
 fail=false;await nodes.find(n=>n.type==='button'&&n.props.children==='Create separate copy').props.onClick();nodes=h.render(props);
 assert.deepEqual(calls[0],calls[1]);assert.equal(calls[1].body.revision,3);assert.equal(created[0].id,'recovered');assert.equal(source.revision,3);assert.ok(nodes.some(n=>n.props?.role==='status'));
});

test('families retain immediate comparison parents, archived roots and recovered history',()=>{
 const plans=[source,{...source,id:'option',parent_id:'base'},{...source,id:'nested',parent_id:'option'},{...source,id:'recovered',recovered_from:{workspace_id:'nested',revision:2}},{...source,id:'independent',parent_id:null},{...source,id:'orphan',parent_id:'missing'}];
 plans[0]={...source,archived:true};const before=plain(plans);
 const families=plain(lifecycle.planFamilies(plans));
 assert.deepEqual(families.map(g=>g.plans.map(p=>p.id)),[['base','option','nested','recovered'],['independent'],['orphan']]);
 assert.deepEqual(plans,before);assert.equal(plans[2].parent_id,'option');
 const cyclic=[{...source,id:'a',parent_id:'b'},{...source,id:'b',parent_id:'a'}];assert.equal(lifecycle.planFamilies(cyclic).length,1);
});

test('historical notices distinguish changed revisions, archive and unavailable plans',()=>{
 const intent={baseline_id:'base',proposed_id:'option',baseline_revision:3,proposed_revision:1,months:2,seed:42,target:0};
 const option={...source,id:'option',revision:1};assert.equal(lifecycle.revisionNotices(intent,[source,option]).length,0);
 const notes=plain(lifecycle.revisionNotices(intent,[{...source,revision:4,archived:true}]));
 assert.equal(notes.length,3);assert.match(notes[0],/saved r3; current r4/);assert.match(notes[1],/archived/);assert.match(notes[2],/unavailable/);assert.equal(intent.baseline_revision,3);
});

test('opening a completed comparison keeps saved results when current plans change',async()=>{
 const band={low:[0,-4000],median:[0,-4000],high:[0,-4000]};
 const run={id:'saved-run',created_at:'2026-10-15',currency:'USD',shared_engine_commit:'test-engine',baseline:{...source},proposed:{...source,id:'option',revision:1},intent:{baseline_id:'base',proposed_id:'option',baseline_revision:3,proposed_revision:1,months:2,seed:42,target:0},payload:{difference:{profit:band},baseline:{bands:{profit:band},probabilities:{},warnings:[]},proposed:{bands:{profit:band},probabilities:{},warnings:[]},probability_positive:{profit:{estimate:0,lower:0,upper:.1}}}};
 const frozen=plain(run),requests=[];const request=async path=>{requests.push(path);return path==='/runs'?{runs:[run]}:run;};
 const h=harness('LabAnalysis.tsx','LabAnalysis',{'./lifecycle':lifecycle,'./LabFinanceDetail':{LabFinanceDetail:()=>null},'./ComparisonSummary':{ComparisonSummary:()=>null}}),props={plans:[source,run.proposed],request,reload:async()=>{},onDirty:()=>{},historyOnly:true};
 h.render(props);await h.settle();let nodes=h.render(props);
 await nodes.find(n=>n.type==='button').props.onClick();nodes=h.render(props);
 assert.ok(!nodes.some(n=>n.props?.['aria-label']==='Historical comparison notice'));
 nodes=h.render({...props,plans:[{...source,revision:4},run.proposed]});
 assert.ok(nodes.some(n=>n.props?.['aria-label']==='Historical comparison notice'));
 assert.deepEqual(run,frozen);assert.deepEqual(requests,['/runs','/runs/saved-run']);
});

test('decision retry retains identity but an edited decision starts a new request',async()=>{
 const calls=[];const request=async(path,method,body)=>{if(method==='POST'){calls.push(plain(body));throw Error('Connection lost');}return {input:{staffing_capacity_enabled:false,scenario:{operating:{roles:[{id:'sales',people:4,salary:6000,wage:0,shifts:1,scope:'rooftop'}]}}}};};
 const h=harness('DecisionChange.tsx','DecisionChange'),props={plan:source,template:staffing,request,onDirty(){},onBusy(){},onBack(){},onCreated:async()=>{}};
 h.render(props);await h.settle();let nodes=h.render(props);
 await nodes.find(n=>n.type==='form').props.onSubmit({preventDefault(){}});nodes=h.render(props);
 await nodes.find(n=>n.type==='form').props.onSubmit({preventDefault(){}});nodes=h.render(props);
 assert.equal(calls[0].request_id,calls[1].request_id);
 nodes.find(n=>n.type==='input'&&n.props.value===5).props.onChange({target:{value:'7'}});nodes=h.render(props);
 await nodes.find(n=>n.type==='form').props.onSubmit({preventDefault(){}});
 assert.notEqual(calls[1].request_id,calls[2].request_id);assert.equal(calls[2].values.people,7);
});

test('history filters retain distinct currencies and horizons and never rewrite runs',()=>{
 const option={...source,id:'option',parent_id:'base'},nested={...source,id:'nested',parent_id:'option'};
 const intent={baseline_id:'base',proposed_id:'option',baseline_revision:3,proposed_revision:1,months:2,seed:42,target:0};
 const old={id:'old',created_at:'2026-10-14T10:00:00Z',currency:'USD',intent};
 const recent={...old,id:'recent',created_at:'2026-10-15T10:00:00Z'};
 const cad={...recent,id:'cad',currency:'CAD'},long={...recent,id:'long',intent:{...intent,months:12}},child={...recent,id:'child',intent:{...intent,baseline_id:'option',proposed_id:'nested'}},other={...recent,id:'other',intent:{...intent,baseline_id:'elsewhere',proposed_id:'unavailable'}};
 const runs=[old,recent,cad,long,child,other],before=plain(runs),plans=[source,option,nested];
 const filtered=plain(lifecycle.filterRuns(runs,plans,{family:'base',months:'2',currency:'USD',latest:true}));
 assert.deepEqual(filtered.map(r=>r.id).sort(),['child','recent']);
 assert.equal(lifecycle.filterRuns(runs,plans,{family:'',months:'',currency:'',latest:true}).length,5);
 assert.equal(lifecycle.filterRuns(runs,plans,{family:'',months:'',currency:'',latest:false}).length,6);
 assert.equal(lifecycle.filterRuns(runs,plans,{family:'missing',months:'',currency:'',latest:false}).length,0);
 assert.deepEqual(runs,before);
});

test('mix editor invalidates previews on edit and preserves exact preview on save failure',async()=>{
 const mix={seed:42,vehicle_count:10,customer_count:20,templates:[{make:'Synthetic',share:100,locked:false}],customers:[{label:'Synthetic',share:100,locked:false}],inventory:[],people:[]};
 const plan={...source,model_definition:{mix}},calls=[],dirty=[],saved=[];let fail=true;
 const request=async(path,method,body)=>{if(!method)return {workspace:plan,mix,bodies:['Sedan'],mode:'hybrid',currency:'USD',rooftops:2,bhph:false};calls.push({path,body:plain(body)});if(path.endsWith('/preview'))return {token:'exact-preview',mix:{...body.draft,inventory:[{id:'SYN-STOCK-0001',make:'Synthetic'}]},segments:{},finance:{},basis:'Synthetic',shared_engine_commit:'test'};if(fail)throw Error('Save failed');return {...plan,revision:4,model_definition:{mix:body.draft}};};
 const h=harness('LabMix.tsx','LabMix'),props={plan,request,onSaved:p=>saved.push(p),onDirty:v=>dirty.push(v),onBusy:()=>{}};
 h.render(props);await h.settle();let nodes=h.render(props);
 nodes.find(n=>n.type==='button'&&n.props.children==='Preview generation').props.onClick();await h.settle();nodes=h.render(props);
 assert.equal(calls.length,1);assert.equal(dirty.at(-1),true);assert.equal(saved.length,0);
 nodes.find(n=>n.type==='input'&&n.props.value===42).props.onChange({target:{value:'43'}});nodes=h.render(props);
 assert.ok(!nodes.some(n=>n.type==='button'&&n.props.children==='Save this exact preview'));
 nodes.find(n=>n.type==='button'&&n.props.children==='Preview generation').props.onClick();await h.settle();nodes=h.render(props);
 nodes.find(n=>n.type==='button'&&n.props.children==='Save this exact preview').props.onClick();await h.settle();nodes=h.render(props);
 assert.ok(nodes.some(n=>n.props?.role==='alert'));assert.equal(saved.length,0);assert.equal(dirty.at(-1),true);
 fail=false;nodes.find(n=>n.type==='button'&&n.props.children==='Save this exact preview').props.onClick();await h.settle();nodes=h.render(props);
 assert.deepEqual(calls[2].body,calls[3].body);assert.equal(calls[3].body.token,'exact-preview');assert.equal(calls[3].body.draft.seed,43);assert.equal(saved.length,1);assert.equal(dirty.at(-1),false);assert.equal(mix.seed,42);
});

test('procedure destination filters documents and carries selected comparison into creation',async()=>{
 const calls=[];const docs=[{id:'p',kind:'procedure',department:'sales',title:'Sales procedure',status:'draft',edition:1,revision:1},{id:'w',kind:'workbook',department:'sales',title:'Sales workbook',status:'draft',edition:1,revision:1}];
 const catalog={templates:{leadership:['Leadership',[], '','']},departments:{leadership:['Leadership',[]],sales:['Sales',[]]}};
 const request=async(path,method,body)=>{if(method==='POST'){calls.push(plain(body));throw Error('Synthetic stop after request');}return path==='/runs'?{runs:[{id:'selected-run',created_at:'2026-10-15',currency:'USD',intent:{months:2}}]}:{catalog,notebooks:docs};};
 const h=harness('LabNotebooks.tsx','LabNotebooks'),props={request,onDirty(){},onBusy(){},fixedKind:'procedure',initialRunId:'selected-run'};
 h.render(props);await h.settle();let nodes=h.render(props);
 assert.ok(nodes.some(n=>n.type==='h3'&&n.props.children==='Sales procedure'));assert.ok(!nodes.some(n=>n.type==='h3'&&n.props.children==='Sales workbook'));
 nodes.find(n=>n.type==='button'&&n.props.children==='Create notebook').props.onClick();await h.settle();
 assert.deepEqual(calls[0],{run_id:'selected-run',department:'leadership',kind:'procedure'});
});


test('goal preview is explicit, edits invalidate it and failed adoption retains retry identity',async()=>{
 const calls=[],created=[],dirty=[];let fail=true;
 const preview={id:'goal-preview',source_revision:3,source_hash:'hash',shared_engine_commit:'chrono',metric:'vehicle_revenue',target:600000,months:12,basis:'Requirements only',proposal:{input:{profile:{currency:'USD'}},changes:[{label:'Required leads',before:10,after:20}]},result:{terminal_expected:{revenue:6000000},warnings:[]},stress:{terminal_expected:{revenue:4000000},warnings:[]}};
 const request=async(path,method,body)=>{calls.push({path,body:plain(body)});if(path.endsWith('/preview'))return preview;if(fail)throw Error('Temporary failure');return {...source,id:'goal-option',parent_id:'base'};};
 const h=harness('LabGoals.tsx','LabGoals'),props={plan:source,request,onCreated:p=>created.push(p),onDirty:v=>dirty.push(v),onBusy(){}};
 let nodes=h.render(props);nodes.find(n=>n.type==='form').props.onSubmit({preventDefault(){}});await h.settle();nodes=h.render(props);
 assert.equal(calls.length,1);assert.equal(created.length,0);
 assert.match(nodes.find(n=>n.props.role==='status').props.children,/falls short/);
 nodes.find(n=>n.type==='input'&&n.props.value===42).props.onChange({target:{value:'43'}});nodes=h.render(props);
 assert.ok(!nodes.some(n=>n.type==='button'&&n.props.children==='Create separate goal option'));
 nodes.find(n=>n.type==='form').props.onSubmit({preventDefault(){}});await h.settle();nodes=h.render(props);
 nodes.find(n=>n.type==='button'&&n.props.children==='Create separate goal option').props.onClick();await h.settle();nodes=h.render(props);
 assert.equal(created.length,0);assert.equal(dirty.at(-1),true);assert.ok(nodes.some(n=>n.props.role==='alert'));
 fail=false;nodes.find(n=>n.type==='button'&&n.props.children==='Create separate goal option').props.onClick();await h.settle();
 assert.deepEqual(calls[2].body,calls[3].body);assert.equal(calls[3].body.preview_id,'goal-preview');assert.equal(calls[1].body.seed,43);assert.equal(created.length,1);assert.equal(dirty.at(-1),false);
});

test('saved goal history reopens frozen outcomes without recalculation and blocks stale adoption',async()=>{
 const calls=[],dirty=[];
 const saved={id:'historical-goal',source_revision:1,source_hash:'old-hash',shared_engine_commit:'old-engine',metric:'contribution',target:1000,months:2,seed:7,sales_per_person:12,can_adopt:false,adopted_option:null,basis:'Frozen',proposal:{input:{profile:{currency:'USD'}},changes:[]},result:{terminal_expected:{contribution:1800},warnings:[]},stress:{terminal_expected:{contribution:1200},warnings:[]}};
 const request=async(path,method)=>{calls.push({path,method});return path.endsWith('/goals')?{previews:[{...saved,created_at:'2026-10-15'}]}:saved;};
 const h=harness('LabGoals.tsx','LabGoals'),props={plan:source,request,onCreated(){},onDirty:v=>dirty.push(v),onBusy(){}};
 let nodes=h.render(props);nodes.find(n=>n.type==='button'&&n.props.children==='Load saved previews').props.onClick();await h.settle();nodes=h.render(props);
 nodes.find(n=>n.type==='button'&&Array.isArray(n.props.children)&&n.props.children[0]==='Open ').props.onClick();await h.settle();nodes=h.render(props);
 assert.equal(calls.length,2);assert.ok(calls.every(c=>c.method===undefined));
 assert.equal(nodes.find(n=>n.type==='button'&&n.props.children==='Create separate goal option').props.disabled,true);
 assert.ok(nodes.some(n=>n.type==='input'&&n.props.value===7));assert.equal(dirty.at(-1),false);
 assert.match(nodes.find(n=>n.props.role==='status').props.children,/falls short/);
});

test('notebook review filter uses server cues without changing saved documents',async()=>{
 const books=[{id:'due',kind:'procedure',department:'sales',title:'Due procedure',status:'draft',edition:1,revision:1},{id:'fresh',kind:'procedure',department:'sales',title:'Fresh procedure',status:'draft',edition:1,revision:1}];
 const data={catalog:{templates:{},departments:{sales:['Sales',[]]}},notebooks:books,review_states:{due:{needs_attention:true,notices:['Follow-up overdue: 2000-01-01']},fresh:{needs_attention:false,notices:[]}}};
 const request=async path=>path==='/runs'?{runs:[]}:data;
 const h=harness('LabNotebooks.tsx','LabNotebooks'),props={request,onDirty(){},fixedKind:'procedure'};
 h.render(props);await h.settle();let nodes=h.render(props);
 assert.ok(nodes.some(n=>n.type==='h3'&&n.props.children==='Fresh procedure'));
 nodes.find(n=>n.type==='input'&&n.props.type==='checkbox').props.onChange({target:{checked:true}});nodes=h.render(props);
 assert.ok(nodes.some(n=>n.type==='h3'&&n.props.children==='Due procedure'));
 assert.ok(!nodes.some(n=>n.type==='h3'&&n.props.children==='Fresh procedure'));
 assert.equal(books.length,2);
});

test('period review retains failed drafts and publishes only after explicit acknowledgement',async()=>{
 const review={id:'review',cadence:'monthly',period:'2026-09',revision:2,status:'draft',notes:'',snapshot:{name:'Test',currency:'USD',workspace_revision:3,report_revision:1,basis:'Reported only',gaps:['Missing data'],rows:[],fields:{}}};
 const calls=[],dirty=[];let fail=true;
 const request=async(path,method,body)=>{if(method){calls.push(plain(body));if(fail)throw Error('Temporary save error');return {...review,notes:body.notes,status:'published',revision:3,published_at:'2026-10-15'};}return path.endsWith('/reports')?{revision:1}:{can_manage:true,scope:'Private',reviews:[review]};};
 const h=harness('LabPeriodReviews.tsx','LabPeriodReviews'),props={plan:source,request,onDirty:v=>dirty.push(v),onBusy(){}};
 h.render(props);await h.settle();let nodes=h.render(props);nodes.find(n=>n.type==='button'&&Array.isArray(n.props.children)&&n.props.children[0]==='Open ').props.onClick();nodes=h.render(props);
 nodes.find(n=>n.type==='textarea').props.onChange({target:{value:'Controller to provide missing September figures.'}});nodes=h.render(props);
 assert.equal(nodes.find(n=>n.type==='button'&&n.props.children==='Publish private review').props.disabled,true);
 nodes.find(n=>n.type==='input'&&n.props.type==='checkbox').props.onChange({target:{checked:true}});nodes=h.render(props);
 nodes.find(n=>n.type==='button'&&n.props.children==='Publish private review').props.onClick();await h.settle();nodes=h.render(props);
 assert.equal(nodes.find(n=>n.type==='textarea').props.value,'Controller to provide missing September figures.');assert.equal(dirty.at(-1),true);
 fail=false;nodes.find(n=>n.type==='button'&&n.props.children==='Publish private review').props.onClick();await h.settle();nodes=h.render(props);
 assert.deepEqual(calls[0],calls[1]);assert.equal(calls[1].revision,2);assert.equal(calls[1].reviewed,true);
 assert.ok(!nodes.some(n=>n.type==='textarea'));assert.equal(dirty.at(-1),false);
});

test('report calibration opens only the explicitly saved hybrid option',async()=>{
 const calls=[],opened=[];let reloads=0;
 const data={revision:1,rows:[],template:'',fields:{},roofs:[],imports:[],kpis:[],outlooks:[]};
 const request=async(path,method,body)=>{if(!method)return data;calls.push({path,body:plain(body)});return path.endsWith('/calibration')?{token:'frozen-preview',month:'2026-09',limitations:'Reported scope only',changes:[]}:{id:'hybrid-option',name:'Hybrid'};};
 const h=harness('LabReports.tsx','LabReports'),props={plan:source,request,onDirty(){},onCreated:async()=>{reloads++;},onOpenOption:id=>opened.push(id)};
 h.render(props);await h.settle();let nodes=h.render(props);
 nodes.find(n=>n.type==='button'&&n.props.children==='Preview calibration for selected scope').props.onClick();await h.settle();nodes=h.render(props);
 assert.equal(reloads,0);assert.deepEqual(opened,[]);
 nodes.find(n=>n.type==='button'&&n.props.children==='Save separate hybrid option').props.onClick();await h.settle();nodes=h.render(props);
 assert.equal(reloads,1);assert.deepEqual(opened,[]);assert.equal(calls[1].body.token,'frozen-preview');assert.equal(calls[1].body.workspace_revision,3);
 nodes.find(n=>n.type==='button'&&n.props.children==='Review saved hybrid option →').props.onClick();assert.deepEqual(opened,['hybrid-option']);
 h.render({...props,plan:{...source,id:'another-source'}});await h.settle();nodes=h.render({...props,plan:{...source,id:'another-source'}});
 assert.ok(!nodes.some(n=>n.type==='button'&&n.props.children==='Review saved hybrid option →'));
});

test('stacked real decision requires explicit hybrid acknowledgement before saving',async()=>{
 const calls=[];
 const model={decision_requires_hybrid:true,input:{operating_enabled:true,staffing_capacity_enabled:false,scenario:{spend:0,operating:{roles:[]}}}};
 const request=async(path,method,body)=>{if(!method)return model;calls.push(plain(body));return {...source,id:'hybrid-child'};};
 const h=harness('DecisionChange.tsx','DecisionChange'),props={plan:source,template:{id:'cost',title:'Extra expense',fields:[['monthly_cost','Monthly expense',0,1000000,100]],help:'Test expense'},request,onDirty(){},onBusy(){},onBack(){},onCreated:async()=>{}};
 h.render(props);await h.settle();let nodes=h.render(props);
 const save=()=>nodes.find(n=>n.type==='button'&&n.props.children==='Save option & review comparison →');
 assert.equal(save().props.disabled,true);
 await nodes.find(n=>n.type==='form').props.onSubmit({preventDefault(){}});assert.equal(calls.length,0);
 nodes.find(n=>n.type==='input'&&n.props.type==='checkbox').props.onChange({target:{checked:true}});nodes=h.render(props);
 assert.equal(save().props.disabled,false);
 await nodes.find(n=>n.type==='form').props.onSubmit({preventDefault(){}});
 assert.equal(calls.length,1);assert.equal(calls[0].acknowledge_hybrid,true);assert.equal(calls[0].revision,3);
});

test('finance CSV preserves both server paths, adjustments and historical engine provenance',()=>{
 const scope={exports:{}};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../components/lab/financeExport.ts',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS}}).outputText,scope);
 const detail={run_id:'saved-run',shared_engine_commit:'old-engine',replay_engine_commit:'verified-new-engine',basis:'Illustrative, not median',currency:'USD',seed:42,trial:0,sides:{baseline:{monthly:[{month:1,profit:-12.25,cash_balance:0}],assumptions:{opening_cash:100,capex:50}},proposed:{monthly:[{month:1,profit:8.5,cash_balance:250}],assumptions:{opening_cash:200}}}};
 const before=JSON.stringify(detail),csv=scope.exports.financeCsv(detail,'wrong-run');
 const lines=csv.split('\r\n');assert.equal(lines.length,3);
 assert.match(lines[0],/"assumption_opening_cash","assumption_capex"/);
 assert.ok(lines[1].startsWith('"saved-run","old-engine","verified-new-engine","Illustrative, not median","USD","42","0","baseline"'));
 assert.ok(lines[1].endsWith('"1","-12.25","0","100","50"'));
 assert.ok(lines[2].endsWith('"1","8.5","250","200",""'));
 assert.equal(JSON.stringify(detail),before);
});

test('detailed starting figures show the saved model revision and direct editor continuation',()=>{
 const destinations=[];
 const h=harness('StartingFigures.tsx','StartingFigures');
 const plan={...source,revision:7,model_definition:{profile:{currency:'USD'}},sections:{identity:{values:{},basis:'assumed',note:'',reviewed_hash:null}}};
 const props={plan,definitions:{identity:{title:'Identity',fields:{},description:''}},request:async()=>{throw Error('Unexpected save');},onSaved(){},onDirty(){},onBusy(){},onContinue:()=>destinations.push('change'),canContinue:true,onSetup:()=>destinations.push('setup'),onOperating:()=>destinations.push('operating')};
 const nodes=h.render(props);
 assert.ok(nodes.some(n=>n.type==='span'&&n.props.children==='Detailed model · revision 7'));
 assert.ok(!nodes.some(n=>n.type==='form'));
 for(const label of ['Review setup & data sources','Review departments & operating plan','Continue to your change →'])nodes.find(n=>n.type==='button'&&n.props.children===label).props.onClick();
 assert.deepEqual(destinations,['setup','operating','change']);
});

test('setup review returns to the selected decision and same source plan',async()=>{
 const h=workspace(),props={navigationHost:{}};h.render(props);await h.settle();let nodes=h.render(props);
 nodes.find(n=>n.type==='button'&&n.props.className==='decisionCard').props.onClick();nodes=h.render(props);
 nodes.find(n=>n.type===StartingFigures).props.onSetup();nodes=h.render(props);
 const setup=nodes.find(n=>typeof n.props.onReports==='function');assert.equal(setup.props.plan.id,'base');
 setup.props.onContinue();nodes=h.render(props);
 const figures=nodes.find(n=>n.type===StartingFigures);assert.equal(figures.props.canContinue,true);assert.equal(figures.props.plan.id,'base');
 figures.props.onContinue();nodes=h.render(props);assert.equal(nodes.find(n=>n.type===DecisionChange).props.template.id,'staffing');
});


test('public references show unavailable values and never adopt assumptions',async()=>{
 const calls=[];const plan={id:'reference-plan',revision:3};
 const data={workspace_id:plan.id,revision:3,name:'Saved baseline',basis:'Historical employer aggregates',reference_hash:'a'.repeat(64),source_hash:'b'.repeat(64),shared_engine_commit:'saved-engine',provenance:{commit:'source-commit'},comparison:{period:'2023',checked:'2026-01-01',source:'Census',industry:'441120',notes:['Missing values are not zero.'],rows:[{name:'Local unavailable',available:false,weight:0,reason:'Suppressed'}],blend:{people:2,inventory:0,annual_pay_per_employee:100,monthly_payroll_proxy:20,monthly_payroll_per_vehicle:null}}};
 const request=async(path,method)=>{calls.push([path,method]);return data;};
 const h=harness('LabReferences.tsx','LabReferences');h.render({plan,request});await h.settle();let tree=h.render({plan,request});
 const text=tree.flatMap(n=>[n.props?.children].flat(Infinity)).filter(n=>typeof n==='string').join(' ');
 assert.ok(text.includes('Suppressed'));assert.ok(text.includes('Unavailable'));assert.ok(text.includes('Historical USD'));
 assert.deepEqual(calls,[[`/workspaces/${plan.id}/references?revision=3`,undefined]]);
 assert.deepEqual(tree.filter(n=>n.type==='button').map(n=>n.props.children),['Download reference snapshot']);
 tree=h.render({plan:{...plan,revision:4},request});
 assert.ok(tree.some(n=>typeof n.props?.children==='string'&&n.props.children.startsWith('Loading historical references')));
});

test('synthetic register loads explicitly and paginates without recalculating rows',async()=>{
 const calls=[];const deals=Array.from({length:51},(_,i)=>({id:'SYN-'+i,month:1,vehicle:'Synthetic vehicle',condition:'used',price:123,cash_at_sale:23,amount_financed:100}));
 const register={label:'Not actual transactions',total_deals:51,truncated:false,deals};
 const snapshot={run_id:'run-fixture',currency:'USD',seed:42,trial:0,shared_engine_commit:'old',replay_engine_commit:'new',sides:{baseline:{register},proposed:{register}}};
 const request=async(path)=>{calls.push(path);return snapshot;};const h=harness('LabSalesRegister.tsx','LabSalesRegister'),props={runId:'run-fixture',request};
 let tree=h.render(props);assert.equal(calls.length,0);
 await tree.find(n=>n.type==='button'&&n.props.children==='Load synthetic sales register').props.onClick();tree=h.render(props);
 assert.deepEqual(calls,['/runs/run-fixture/finance-detail?include_register=true']);assert.equal(tree.filter(n=>n.type==='tr').length,51);
 tree.find(n=>n.type==='CollectionPagination').props.onPageChange(1);tree=h.render(props);
 assert.equal(tree.filter(n=>n.type==='tr').length,2);assert.ok(tree.some(n=>n.type==='td'&&n.props.children==='SYN-50'));
 tree.find(n=>n.type==='select').props.onChange({target:{value:'baseline'}});tree=h.render(props);assert.equal(tree.filter(n=>n.type==='tr').length,51);assert.equal(calls.length,1);
});


test('experiment import previews once, requires explicit save and retains retry context',async()=>{
 const h=harness('LabExperimentImport.tsx','LabExperimentImport'),calls=[],created=[],dirty=[];
 let fail=true;
 const preview={preview_id:'LABI-1',input:{name:'Composite plan',profile:{name:'Fixture',country:'United States',region:'Texas',currency:'USD'},dealership:{kind:'BHPH'},rooftops:2,months:3},provenance:{file_sha256:'abc',claimed_data_path:'hybrid'},warnings:['Unverified inputs']};
 const props={busy:false,onDirty:v=>dirty.push(v),onBusy:()=>{},onCreated:w=>created.push(w),request:async(path,method,body)=>{calls.push({path,body});if(path.endsWith('/preview'))return preview;if(fail)throw new Error('Temporary failure');return {id:'NEW'};}};
 let nodes=h.render(props);const file={size:123,text:async()=>'{"input":{}}'};
 nodes.find(n=>n.type==='input'&&n.props.type==='file').props.onChange({target:{files:[file],value:'file'}});
 await h.settle();nodes=h.render(props);assert.equal(calls.length,1);assert.equal(created.length,0);assert.equal(dirty.at(-1),true);
 nodes.find(n=>n.type==='button'&&n.props.children==='Import & review setup').props.onClick();await h.settle();nodes=h.render(props);
 assert.equal(nodes.find(n=>n.props?.role==='alert').props.children,'Temporary failure');assert.equal(created.length,0);
 fail=false;nodes.find(n=>n.type==='button'&&n.props.children==='Import & review setup').props.onClick();await h.settle();nodes=h.render(props);
 assert.deepEqual(plain(calls[1].body),plain(calls[2].body));assert.equal(created[0].id,'NEW');assert.equal(dirty.at(-1),false);
 assert.ok(!nodes.some(n=>n.type==='button'&&n.props.children==='Import & review setup'));
});

test('experiment import refuses oversized files before sending content',async()=>{
 const h=harness('LabExperimentImport.tsx','LabExperimentImport');let calls=0;
 const props={busy:false,onDirty:()=>{},onBusy:()=>{},onCreated:()=>{},request:async()=>{calls++;}};
 let nodes=h.render(props);nodes.find(n=>n.type==='input'&&n.props.type==='file').props.onChange({target:{files:[{size:1000001,text:async()=>{throw new Error('should not read');}}],value:'file'}});
 await h.settle();nodes=h.render(props);assert.equal(calls,0);assert.match(nodes.find(n=>n.props?.role==='alert').props.children,/1 MB/);
});

test('compact figures keep unsaved values until an explicit section discard',()=>{
 const h=harness('StartingFigures.tsx','StartingFigures');
 const section=(name)=>({values:{name},basis:'assumed',note:'Synthetic source note',reviewed_hash:null});
 const plan={...source,model_definition:null,sections:{identity:section('Original'),software:section('Software')}};
 const definition={title:'Section',description:'',fields:{name:['Name','text']}};
 const props={plan,definitions:{identity:definition,software:definition},request:async()=>{throw Error('Unexpected save');},onSaved(){},onDirty(){},onBusy(){},onContinue(){},canContinue:true};
 let nodes=h.render(props);
 nodes.find(n=>n.type==='input').props.onChange({target:{value:'Unsaved'}});nodes=h.render(props);
 nodes.find(n=>n.type==='nav').props.children[1].props.onClick();nodes=h.render(props);
 assert.equal(nodes.find(n=>n.type==='input').props.value,'Unsaved');
 nodes.find(n=>n.type==='button'&&n.props.children==='Keep editing figures').props.onClick();nodes=h.render(props);
 assert.equal(nodes.find(n=>n.type==='input').props.value,'Unsaved');
 nodes.find(n=>n.type==='nav').props.children[1].props.onClick();nodes=h.render(props);
 nodes.find(n=>n.type==='button'&&n.props.children==='Discard figures and open section').props.onClick();nodes=h.render(props);
 assert.equal(nodes.find(n=>n.type==='input').props.value,'Software');
 assert.equal(plan.sections.identity.values.name,'Original');
 assert.ok(!nodes.some(n=>n.props.role==='alert'));
});

test('saved goal replacement retains edits on cancellation and failed fetch',async()=>{
 let fail=true;const dirty=[];
 const saved={id:'saved',metric:'vehicle_revenue',target:1000,months:2,seed:7,sales_per_person:12,source_revision:1,can_adopt:false,basis:'Frozen',proposal:{input:{profile:{currency:'USD'}},changes:[]},result:{terminal_expected:{revenue:2000},warnings:[]},stress:{terminal_expected:{revenue:1800},warnings:[]}};
 const request=async(path)=>{if(path.endsWith('/goals'))return {previews:[{...saved,created_at:'2026-10-15'}]};if(fail)throw Error('Unavailable saved preview');return saved;};
 const h=harness('LabGoals.tsx','LabGoals'),props={plan:source,request,onCreated(){},onDirty:v=>dirty.push(v),onBusy(){}};
 let nodes=h.render(props);nodes.find(n=>n.type==='button'&&n.props.children==='Load saved previews').props.onClick();await h.settle();nodes=h.render(props);
 nodes.find(n=>n.type==='input'&&n.props.value===600000).props.onChange({target:{value:'750000'}});nodes=h.render(props);
 const open=()=>nodes.find(n=>n.type==='button'&&Array.isArray(n.props.children)&&n.props.children[0]==='Open ').props.onClick();
 open();nodes=h.render(props);nodes.find(n=>n.type==='button'&&n.props.children==='Keep editing goal').props.onClick();nodes=h.render(props);
 assert.ok(nodes.some(n=>n.type==='input'&&n.props.value===750000));
 open();nodes=h.render(props);nodes.find(n=>n.type==='button'&&n.props.children==='Open saved goal inputs').props.onClick();await h.settle();nodes=h.render(props);
 assert.ok(nodes.some(n=>n.type==='input'&&n.props.value===750000));assert.equal(dirty.at(-1),true);
 assert.ok(nodes.some(n=>n.props.role==='alert'&&n.props.children==='Unavailable saved preview'));
 fail=false;nodes.find(n=>n.type==='button'&&n.props.children==='Open saved goal inputs').props.onClick();await h.settle();nodes=h.render(props);
 assert.ok(nodes.some(n=>n.type==='input'&&n.props.value===1000));assert.equal(dirty.at(-1),false);
 assert.ok(!nodes.some(n=>n.type==='button'&&n.props.children==='Open saved goal inputs'));
});
