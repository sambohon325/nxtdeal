import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const scope={exports:{},require:()=>({PRODUCT_ACCENT_COLORS:[]})};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../components/InventoryWorkspaceBoard.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,scope);
test('inventory retains vehicles recorded under noncatalog stages without duplicate stages',()=>{
 assert.deepEqual(Array.from(scope.exports.inventoryStageNames(['Acquired','Recon'],{Recon:[],Legacy:[{vehicle_id:'V1'}],Unknown:[]})),['Acquired','Recon','Legacy','Unknown']);
});

const daily={exports:{},require:()=>({})};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../components/InventoryDay.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,daily);
test('inventory daily actions respect the supplied menu access',()=>{
 assert.deepEqual(Array.from(daily.exports.inventoryDayActions(new Set(['pricing','merchandising'])),a=>a.key),['pricing','merchandising']);
 assert.equal(daily.exports.inventoryDayActions(new Set()).length,0);
});

test('responsibility edits preserve omitted roles, remove cleared assignments and skip unchanged values',()=>{
 const result=scope.exports.ownershipChanges({buyer:'  ', recon_manager:' EMP-2 ', sales_manager:'EMP-3'}, {buyer:'EMP-1',inventory_manager:'EMP-4',sales_manager:'EMP-3'});
 assert.deepEqual(JSON.parse(JSON.stringify(result)),{buyer:'',recon_manager:'EMP-2'});
 assert.deepEqual(Object.keys(scope.exports.ownershipChanges({buyer:'  '},{buyer:null})),[]);
});
