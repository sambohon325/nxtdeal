import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
function render(items,active,expanded=false){
 const scope={exports:{},require:n=>n==='react'?{useState:()=>[expanded,()=>{}]}:n==='react/jsx-runtime'?jsx:{}};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../components/DepartmentDailyNavigation.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,scope);
 return scope.exports.DepartmentDailyNavigation({department:'Inventory',items,active});
}
const items=Array.from({length:12},(_,i)=>({key:`work-${i}`,label:`Work ${i}`,onSelect:()=>i}));
test('daily navigation only renders permitted destinations and hides empty catalogs',()=>{
 assert.equal(render([]),null);
 const tree=render(items.slice(0,2),'work-1');
 assert.equal(tree.props['aria-label'],'Inventory daily work');
 const buttons=tree.props.children[1];assert.equal(buttons.length,2);assert.equal(buttons[1].props['aria-current'],'page');assert.equal(buttons[1].props.onClick(),1);
});
test('long workflow catalogs expose all destinations through expansion and retain active overflow context',()=>{
 const collapsed=render(items,'work-8');assert.equal(collapsed.props.children[1].length,4);assert.match(collapsed.props.children[2].props.children,/Work 8/);
 const expanded=render(items,'work-8',true);assert.equal(expanded.props.children[1].length,12);assert.equal(expanded.props.children[1][8].props['aria-current'],'page');
});
