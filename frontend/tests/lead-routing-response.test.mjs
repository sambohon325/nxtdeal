import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
function client(data,ok=true){
 const scope={exports:{},fetch:async()=>({ok,json:async()=>data}),require:id=>id==='@/lib/auth'?{authHeaders:()=>({})}:{API_BASE:''}};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../lib/leadRouting.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,scope);
 return scope.exports;
}
test('routing preview accepts a match with null error',async()=>{
 const result=await client({matched:true,would_assign_to:'EMP-1',error:null}).previewRoute({Source:'Website'});
 assert.equal(result.would_assign_to,'EMP-1');
});
test('routing preview keeps an unresolved roster explanation',async()=>{
 const result=await client({matched:true,error:'No eligible employee'}).previewRoute({});
 assert.equal(result.error,'No eligible employee');
});
test('routing HTTP and API errors still reject',async()=>{
 await assert.rejects(client({error:'Denied'},false).previewRoute({}),/Denied/);
 await assert.rejects(client({error:'Invalid rule'}).createRoutingRule({}),/Invalid rule/);
});
