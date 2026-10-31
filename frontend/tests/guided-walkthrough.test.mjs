import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
function load(url,globals={}){const exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL(url,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports,require:()=>({}),...globals});return exports;}
const content=load('../lib/helpContent.ts');
const targets=load('../lib/departmentTourTargets.ts');
function steps(selectors=[]){return load('../components/GuidedWalkthrough.tsx',{require:name=>name.includes('helpContent')?content:name.includes('departmentTourTargets')?targets:{},document:{querySelectorAll:selector=>selectors.includes(selector)?[{getBoundingClientRect:()=>({width:200,height:44})}]:[]},getComputedStyle:()=>({visibility:'visible'})}).pageSteps;}
test('Read-only overview does not invent form or save controls',()=>{const result=steps()({department:'Operations',title:'Today'});assert.equal(result.length,3);assert.ok(!result.some(s=>s.title==='Work through the fields'));});
test('Contextual tour includes visible search and fields and excludes absent pagination',()=>{const result=steps(['#dealership-content input[type="search"]','#dealership-content .work-field'])({department:'Inventory',title:'Vehicles'});assert.ok(result.some(s=>s.title==='Find the right record'));assert.ok(result.some(s=>s.title==='Work through the fields'));assert.ok(!result.some(s=>s.title==='Use the list controls'));});
test('Every department walkthrough preserves its specific ordered procedure',()=>{for(const [department,guide] of Object.entries(content.helpGuides)){const result=steps()({department,title:department,departmentTour:true,isSystemAdmin:true});assert.equal(result.length,guide.steps.length);assert.deepEqual(Array.from(result,s=>s.text),Array.from(guide.steps));assert.equal(result.at(-1).action,guide.check);}});

test('dealership administration tour does not point at hidden system tools',()=>{
 const result=steps()({department:'Administration',title:'Administration',departmentTour:true});
 assert.ok(result.some(s=>s.title==='Roles & access requests'));
 assert.ok(!result.some(s=>s.title==='System administration'||s.title==='Login security'));
 assert.ok(result.some(s=>s.text.includes('does not grant NXTDeal system access')));
});
