import {test} from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';import ts from 'typescript';
const scope={exports:{},require:()=>({})};vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../components/ServiceDay.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,scope);
const bucket={count:30,repair_orders:Array.from({length:25},(_,i)=>({id:String(i)}))};const data={advisor_dashboard:{my_waiting_customers:bucket,my_pending_approvals:bucket,my_vehicles_ready:bucket},command_center:Object.fromEntries(['open_ros','waiting_approval','waiting_parts','waiting_technician','waiting_delivery','comebacks'].map(k=>[k,bucket]))};
test('advisor queues never surface manager queues without the server manager flag',()=>{assert.equal(scope.exports.serviceQueues({...data,is_manager_view:false}).length,3);assert.equal(scope.exports.serviceQueues({...data,is_manager_view:true}).length,9);});
test('service queues retain every returned record and the total beyond the server summary limit',()=>{const result=scope.exports.serviceQueues(data);assert.equal(result[0].bucket.count,30);assert.equal(result[0].bucket.repair_orders.length,25);assert.equal(result[0].bucket.repair_orders[24].id,'24');});

test('returned unfinished work stays reachable with advisor and manager scope',()=>{
 const expanded={...data,advisor_dashboard:{...data.advisor_dashboard,my_returned_unfinished:bucket},command_center:{...data.command_center,returned_unfinished:bucket}};
 const advisor=scope.exports.serviceQueues({...expanded,is_manager_view:false});
 assert.ok(advisor.some(q=>q.key==='my_returns'));assert.ok(!advisor.some(q=>q.key==='returns'));
 const manager=scope.exports.serviceQueues({...expanded,is_manager_view:true});assert.equal(manager.find(q=>q.key==='returns').bucket.count,30);
});

test('follow-up urgency uses calendar dates without parsing them as UTC timestamps',()=>{
 const today=new Date(2026,9,14,0,15);
 assert.equal(scope.exports.followupDueLabel('2026-10-13',today),'Overdue · 2026-10-13');
 assert.equal(scope.exports.followupDueLabel('2026-10-14',today),'Due today · 2026-10-14');
 assert.equal(scope.exports.followupDueLabel('2026-10-15',today),'Due 2026-10-15');
});

test('daily work opens the actionable repair-order step and retains a general fallback',()=>{
 for(const key of ['my_returns','returns'])assert.equal(scope.exports.serviceQueueAction(key).tab,'followup');
 for(const key of ['approval','waiting_approval'])assert.equal(scope.exports.serviceQueueAction(key).tab,'estimate');
 for(const key of ['ready','waiting_delivery'])assert.equal(scope.exports.serviceQueueAction(key).tab,'pickup');
 for(const key of ['waiting_parts','parts_delayed'])assert.equal(scope.exports.serviceQueueAction(key).tab,'parts');
 assert.equal(scope.exports.serviceQueueAction('open_ros').tab,'overview');
});
