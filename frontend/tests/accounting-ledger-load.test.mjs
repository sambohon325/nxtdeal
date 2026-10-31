import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const source=ts.transpileModule(fs.readFileSync(new URL('../components/LoanAccountingBoard.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
function harness(){
 const effects=[], states=[];
 let resolve,reject;
 const pending=new Promise((yes,no)=>{resolve=yes;reject=no;});
 const scope={exports:{},require:name=>name.endsWith('/WorkspaceUi')?workControls:(name==='react'?{
  useEffect:fn=>effects.push(fn),
  useState:initial=>{const i=states.length;states.push(typeof initial==='function'?initial():initial);return [states[i],v=>{states[i]=typeof v==='function'?v(states[i]):v;}];}
 }:name==='react/jsx-runtime'?{jsx:()=>null,jsxs:()=>null}:name.includes('productTheme')?{PRODUCT_ACCENT_COLORS:[]}:name.includes('loanAccounting')?{getDailyLedger:()=>pending}:{})};
 vm.runInNewContext(source,scope);scope.exports.LoanAccountingBoard({theme:'dark'});
 return {states,start:effects[2],resolve,reject};
}
test('superseded ledger responses cannot replace the selected date',async()=>{
 const h=harness(), cleanup=h.start(); cleanup();
 const old={entries:[{payment_id:'OLD-DATE'}]}; h.resolve(old);
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(h.states.includes(old),false);
});
test('failed ledger load exposes the error and ends loading without payment rows',async()=>{
 const h=harness();h.start();h.reject(new Error('Ledger unavailable'));
 await new Promise(resolve=>setImmediate(resolve));
 assert.ok(h.states.includes('Unable to load this ledger date.')||h.states.includes('Ledger unavailable'));
 assert.equal(h.states[6],false);
 assert.equal(h.states[5],null);
});

test('unposted queue exposes records beyond100 and searches across all pages',()=>{
 const scope={exports:{},require:()=>({PRODUCT_ACCENT_COLORS:[]})};
 vm.runInNewContext(source,scope);
 const rows=Array.from({length:105},(_,i)=>({payment_id:`PAY-${i}`,loan_id:`LOAN-${i}`,payment_date:'2026-10-13',method:'cash'}));
 const page=scope.exports.unpostedPaymentPage;
 assert.deepEqual(Array.from(page(rows,'',26).rows,r=>r.payment_id),['PAY-104']);
 assert.equal(page(rows,' loan-104 ',0).total,1);
 assert.equal(page(rows,'missing',26).current,0);
 assert.equal(page(rows,'',999).current,26);
});

test('period status never assumes open while data is unavailable or selection invalid',()=>{
 const scope={exports:{},require:()=>({PRODUCT_ACCENT_COLORS:[]})};vm.runInNewContext(source,scope);
 const status=scope.exports.accountingPeriodStatus;
 assert.equal(status([],false,2026,10),'unavailable');
 assert.equal(status([],true,2026,13),'unavailable');
 assert.equal(status([],true,26,10),'unavailable');
 assert.equal(status([],true,2026,10),'open');
 assert.equal(status([{period_key:'2026-10',status:'closed'}],true,2026,10),'closed');
});

for (const tab of ['General Ledger','Financial Statements','Bank Reconciliation']) {
 test(`${tab} surfaces a failed grouped load and ignores cancelled responses`,async()=>{
  const effects=[],states=[];let reject;
  const pending=new Promise((_,no)=>{reject=no;});
  const api=new Proxy({}, {get:()=>()=>pending});
  const scope={exports:{},require:name=>name.endsWith('/WorkspaceUi')?workControls:(name==='react'?{
   useEffect:fn=>effects.push(fn),
   useState:initial=>{const i=states.length;states.push(i===0?tab:typeof initial==='function'?initial():initial);return [states[i],v=>{states[i]=typeof v==='function'?v(states[i]):v;}];}
  }:name==='react/jsx-runtime'?{jsx:()=>null,jsxs:()=>null}:name.includes('productTheme')?{PRODUCT_ACCENT_COLORS:[]}:api)};
  vm.runInNewContext(source,scope);scope.exports.LoanAccountingBoard({theme:'dark'});
  const cancel=effects[3]();reject(new Error('Offline'));
  await new Promise(resolve=>setImmediate(resolve));
  const failed=states.find(v=>v?.tab===tab&&v?.error);
  assert.ok(failed);assert.equal(failed.loading,false);
  cancel();
  const cancelRetry=effects[3]();cancelRetry();
  await new Promise(resolve=>setImmediate(resolve));
  assert.ok(states.find(v=>v?.tab===tab&&v?.loading===true));
 });
}

test('bank history searches all records and combines status with linked GL context',()=>{
 const scope={exports:{},require:()=>({PRODUCT_ACCENT_COLORS:[]})};vm.runInNewContext(source,scope);
 const page=scope.exports.bankHistoryPage;
 const rows=Array.from({length:9},(_,i)=>({id:`BANK-${i}`,transaction_date:'2026-10-13',description:'Fictional',status:i===8?'matched':'unmatched',matched_gl_entry_id:i===8?'GLE-9':null}));
 assert.deepEqual(Array.from(page(rows,'','',2).rows,r=>r.id),['BANK-8']);
 assert.equal(page(rows,'matched',' gle-9 ',0).total,1);
 assert.equal(page(rows,'unmatched','GLE-9',0).total,0);
 assert.equal(page(rows,'','missing',9).current,0);
});

test('bank match editor keeps proposed ledger references with their own transaction',()=>{
 const states=[];let cursor=0;
 const scope={exports:{},require:name=>name.endsWith('/WorkspaceUi')?workControls:(name==='react'?{
  useEffect:()=>{},useState:initial=>{const i=cursor++;if(!(i in states))states[i]=typeof initial==='function'?initial():initial;return [states[i],v=>{states[i]=typeof v==='function'?v(states[i]):v;}];}
 }:name==='react/jsx-runtime'?{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})}:name.includes('productTheme')?{PRODUCT_ACCENT_COLORS:[]}:{})};
 vm.runInNewContext(source,scope);
 function render(){cursor=0;return scope.exports.LoanAccountingBoard({theme:'dark'});}
 render();states[0]='Bank Reconciliation';
 const ready=states.findIndex(v=>v&&typeof v==='object'&&v.tab==='Payments Ledger');
 states[ready]={tab:'Bank Reconciliation',loading:false,error:null};
 states[21]={bank_account:{},unmatched_bank_transactions:[{id:'BANK-A'},{id:'BANK-B'}],unmatched_gl_entries:[]};
 function find(tree,label){if(!tree)return null;if(Array.isArray(tree)){for(const child of tree){const found=find(child,label);if(found)return found;}return null;}if(tree.props?.['aria-label']===label)return tree;return find(tree.props?.children,label);}
 find(render(),'Review match for BANK-A').props.onClick();
 find(render(),'Ledger entry for BANK-A').props.onChange({target:{value:'GLE-A'}});
 find(render(),'Review match for BANK-B').props.onClick();
 assert.equal(find(render(),'Ledger entry for BANK-B').props.value,'');
 find(render(),'Ledger entry for BANK-B').props.onChange({target:{value:'GLE-B'}});
 find(render(),'Review match for BANK-A').props.onClick();
 assert.equal(find(render(),'Ledger entry for BANK-A').props.value,'GLE-A');
});
