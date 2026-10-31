import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const source=fs.readFileSync(new URL('../lib/helpContent.ts',import.meta.url),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
const context={exports:{}};vm.runInNewContext(compiled,context);
const {helpGuides,tourSteps}=context.exports;
test('Every core department has prerequisites, a procedure, completion checks and recovery guidance',()=>{
 for(const department of ['Operations','Sales','BDC','Marketing','Inventory','Service','Finance','Administration','Network','Readiness','Extras']){
  const guide=helpGuides[department];assert.ok(guide,department);assert.ok(guide.steps.length>=3,department);for(const field of ['goal','before','check','trouble'])assert.ok(guide[field].length>20,`${department}:${field}`);
 }
});
test('Welcome tour covers orientation, navigation, records, utilities and personalization',()=>{
 assert.equal(tourSteps.length,6);assert.equal(new Set(tourSteps.map(s=>s.target)).size,6);assert.ok(tourSteps.every(s=>s.title&&s.text.length>40));
});
