import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
import {workControls} from './work-controls-stub.mjs';
function load(file,require=()=>({})){const scope={exports:{},require,Error,requestAnimationFrame:fn=>fn()};vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL(file,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,scope);return scope.exports;}
const helpers=load('../lib/marketplaceBrowser.ts');
const pagination=load('../components/CollectionPagination.tsx');
const listing=(id,state='available')=>({id,name:`Tool ${id}`,category:'crm',blurb:'Customer work',phase:'day1',state,capability:'crm',capability_live:false,installed_at:null,installed_by:null});
const fixture={can_manage:true,summary:{total_listings:30,installed:1,connected:0},categories:[{id:'crm',name:'Customer management',section:'day1',purpose:['Customer work'],listings:Array.from({length:30},(_,i)=>listing(String(i).padStart(2,'0'),i===0?'installed':'available'))},{id:'future',name:'Future',section:'phase2',listings:[{...listing('Future','coming_soon'),category:'future'}]}]};
const flatten=node=>!node||typeof node!=='object'?[]:Array.isArray(node)?node.flatMap(flatten):[node,...flatten(node.props?.children)];
function setup(initial=[],fail=false){let cursor=0;const state=initial,refs=[],calls=[];let refIndex=0;const component=load('../components/MarketplaceBoard.tsx',name=>{
 if(name==='react')return {useState:initial=>{const index=cursor++;if(!(index in state))state[index]=initial;return[state[index],value=>state[index]=typeof value==='function'?value(state[index]):value];},useRef:value=>refs[refIndex++]??(refs[refIndex-1]={current:value}),useEffect:()=>{}};
 if(name==='react/jsx-runtime')return jsx;
 if(name==='./WorkspaceUi')return workControls;
 if(name==='./WorkField')return {WorkField:'label'};
 if(name==='./CollectionPagination')return {...pagination,CollectionPagination:'pagination'};
 if(name==='@/lib/marketplaceBrowser')return helpers;
 if(name==='@/lib/marketplace')return {fetchMarketplace:async()=>fixture,installListing:async id=>{calls.push(['install',id]);if(fail)throw Error('Provider rejected setup');return listing(id,'installed');},uninstallListing:async id=>{calls.push(['remove',id]);return listing(id);}};
 return {default:{},OverviewHeader:'header'};
 });return {state,calls,render:()=>{cursor=0;refIndex=0;return flatten(component.MarketplaceBoard({theme:'dark'}));}};
}
test('all views support search and installed view excludes uninstalled listings',()=>{
 assert.equal(helpers.marketplaceRows(fixture,'installed','','','').length,1);
 assert.equal(helpers.marketplaceRows(fixture,'phase2','future','','').length,1);
 assert.equal(helpers.marketplaceRows(fixture,'browse','customer management','','').length,30);
 assert.equal(helpers.marketplaceRows(fixture,'browse','','crm','installed').length,1);
});
test('listing detail return preserves search and page; filters reset the page',()=>{
 const h=setup([fixture,false,'','Tool','','',1]);let tree=h.render();
 assert.equal(tree.filter(n=>n.props?.['aria-label']?.startsWith('View Tool')).length,12);
 tree.find(n=>n.props?.['aria-label']==='View Tool 12 details').props.onClick({currentTarget:{focus(){}}});
 h.state[9]={...listing('12'),category_name:'Customer management',purpose:[]};
 h.render().find(n=>n.props?.children==='Back to results').props.onClick();
 assert.equal(h.state[3],'Tool');assert.equal(h.state[6],1);
 h.render().find(n=>n.type==='input').props.onChange({target:{value:'missing'}});
 assert.equal(h.state[6],0);assert.ok(h.render().some(n=>n.props?.title==='No matching listings'));
});
test('failed installation remains visible and never reports a saved state',async()=>{
 const h=setup([fixture,false,'','','','',0,0,'01',{...listing('01'),category_name:'CRM',purpose:[]}],true);
 await h.render().find(n=>n.props?.children==='Add to dealership').props.onClick();
 assert.equal(h.calls.length,1);assert.equal(h.state[9].state,'available');assert.equal(h.state[10],'Provider rejected setup');
});
test('removal requires a reviewed second action and dealership viewers have no mutation button',async()=>{
 const h=setup([fixture,false,'','','','',0,0,'00',{...listing('00','installed'),category_name:'CRM',purpose:[]}]);
 await h.render().find(n=>n.props?.children==='Remove listing').props.onClick();assert.equal(h.calls.length,0);
 await h.render().find(n=>n.props?.children==='Confirm removal').props.onClick();assert.deepEqual(h.calls,[['remove','00']]);
 const dealer=setup([{...fixture,can_manage:false},false,'','','','',0,0,'01',{...listing('01'),category_name:'CRM',purpose:[]}]);
 assert.ok(!dealer.render().some(n=>n.props?.children==='Add to dealership'));
});
