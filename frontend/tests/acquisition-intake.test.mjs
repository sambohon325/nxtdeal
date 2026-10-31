import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const scope={exports:{},require:()=>({PRODUCT_ACCENT_COLORS:[]})};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../components/AcquisitionsBoard.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,scope);
const validate=scope.exports.acquisitionIntakeError;
test('intake accepts unknown optional facts and zero values',()=>{
 assert.equal(validate('Fictional','Test','','',''),null);
 assert.equal(validate('Fictional','Test','2024','0','0.00'),null);
});
test('intake rejects incomplete identity and malformed numeric facts instead of truncating',()=>{
 for(const args of [[' ','Test','','',''],['Test',' ','','',''],['Test','Test','24','',''],['Test','Test','','-1',''],['Test','Test','','10.5',''],['Test','Test','','','12abc'],['Test','Test','','','-1'],['Test','Test','','','Infinity'],['Test','Test','','','1.234']]) assert.ok(validate(...args));
});

test('buying queue pages all records, combines stage and search, and clamps stale pages',()=>{
 const records=Array.from({length:9},(_,i)=>({id:`ACQ-${i}`,stage:i===8?'approved':'evaluate',make:'Fictional',model:'Test',vin:i===8?'SYNTHETICVIN':null,linked_deal_id:i===8?'DEAL-9':null}));
 const pages=[0,1,2].flatMap(p=>Array.from(scope.exports.acquisitionQueue(records,'','',p,4).rows,r=>r.id));
 assert.deepEqual(pages,records.map(r=>r.id));
 assert.equal(scope.exports.acquisitionQueue(records,'approved',' syntheticvin ',0).total,1);
 assert.equal(scope.exports.acquisitionQueue(records,'evaluate','DEAL-9',0).total,0);
 assert.equal(scope.exports.acquisitionQueue(records,'','DEAL-9',99).current,0);
 assert.equal(scope.exports.acquisitionQueue([],'','',5).pages,1);
});
