import {test} from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';import ts from 'typescript';
const scope={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../lib/financeDay.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,scope);
const {financeStep,financeQueue}=scope.exports;
test('Finance separates handoffs, decisions, contracts and funding without treating approval as funding',()=>{
 for(const [status,financing_status,queue] of [['desking','not_started',null],['financing','not_started','handoff'],['financing','submitted','response'],['financing','countered','response'],['financing','declined','response'],['financing','approved','contract'],['contract','approved','funding'],['funded','approved','funded'],['cancelled','declined','cancelled']])assert.equal(financeStep({status,financing_status})?.queue??null,queue);
});
test('Finance search filters only the selected queue and orders oldest updates first without mutating input',()=>{
 const deals=[{id:'new',status:'financing',financing_status:'not_started',customer:{name:'Fictional Sam'},updated_at:'2026-10-12'},{id:'old',status:'financing',financing_status:'not_started',vehicle:{description:'Fictional Demo'},updated_at:'2026-10-11'},{id:'done',status:'funded',customer:{name:'Fictional Sam'},updated_at:'2026-10-10'}];
 assert.equal(financeQueue(deals,'handoff','fictional').map(d=>d.id).join(','),'old,new');assert.equal(deals[0].id,'new');assert.equal(financeQueue(deals,'handoff',' SAM ')[0].id,'new');assert.equal(financeQueue(deals,'handoff','missing').length,0);
});
