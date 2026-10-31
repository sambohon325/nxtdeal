import {workControls} from './work-controls-stub.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
function load(path, dependencies = {}, extra = '') {
 const source=ts.transpileModule(fs.readFileSync(new URL(path,import.meta.url),'utf8')+extra,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const scope={exports:{},require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;if(name==='react/jsx-runtime')return jsx; assert.ok(name in dependencies, name); return dependencies[name];}};
 vm.runInNewContext(source,scope);return scope.exports;
}
const {CustomerVerifyGate}=load('../components/apps/CustomerVerifyGate.tsx');
const {DigitalRetailFlow}=load('../components/DigitalRetailFlow.tsx');
test('customer gate never mounts protected children or asks for identity data',()=>{
 let mounted=false;
 function Private(){mounted=true;return 'PRIVATE CUSTOMER DATA';}
 const html=renderToStaticMarkup(createElement(CustomerVerifyGate,{what:'your service history'},createElement(Private)));
 assert.equal(mounted,false);assert.match(html,/not available yet/);assert.match(html,/your service history/);
 assert.doesNotMatch(html,/PRIVATE|<input|<form|Send code/);
});

const { CustomerLoadError } = load('../components/apps/screens/kit.tsx', {
 'react': {}, '@/lib/apps/registry': {},
});
for (const [file, subject] of [['CustomerMessages','your conversation'], ['MyGarageVehicles','your vehicle records'], ['MyGarageStatus','your service status']]) {
 test(`${file} distinguishes failed reads from missing records and offers retry`, () => {
  let retries=0;
  const { Inner }=load(`../components/apps/screens/${file}.tsx`, {
   './kit': {useAsync:()=>({loading:false,error:'PRIVATE provider error',data:{secret:'STALE customer record'},reload:()=>{retries++;}}),CustomerLoadError},
   '@/lib/garage': {}, '@/components/apps/CustomerVerifyGate': {},
   '@/lib/apps/registry': {accentOf:()=>({})},
  }, '\nexport { Inner };');
  const tree=Inner({app:{}});
  const html=renderToStaticMarkup(tree);
  assert.match(html,/role="alert"/);assert.ok(html.includes(subject));
  assert.doesNotMatch(html,/PRIVATE|STALE|No conversation|find your records/);
  const rendered=tree.type(tree.props);
  rendered.props.children.find(child=>child.type==='button').props.onClick();
  assert.equal(retries,1);
 });
}
test('online buying closed entry renders nothing and open entry is honest and dismissible',()=>{
 assert.equal(DigitalRetailFlow({open:false,onClose(){}}),null);
 let closed=false;const tree=DigitalRetailFlow({open:true,onClose(){closed=true;}});
 const html=renderToStaticMarkup(tree);assert.match(html,/not available yet/);assert.doesNotMatch(html,/<input|<form|demo code|license/i);
 tree.props.children.find(child=>child.type==='button').props.onClick();assert.equal(closed,true);
});
