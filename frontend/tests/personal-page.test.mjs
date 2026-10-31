import {workControls} from './work-controls-stub.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
import { renderToStaticMarkup } from 'react-dom/server';
import { publicHttpsUrl } from '../lib/personalPageLinks.ts';
import { deploymentRedirect } from '../lib/deploymentRouting.ts';
const source=ts.transpileModule(fs.readFileSync(new URL('../components/PersonalPage.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const scope={exports:{},require:name=>name.endsWith('/WorkspaceUi')?workControls:(name==='react/jsx-runtime'?jsx:{publicHttpsUrl})};
vm.runInNewContext(source,scope);
const site={slug:'fixture',headline:'<script>bad()</script>',bio:'<img onerror=bad()>',featured_vehicles:[],branding:{}};
test('external links reject executable, insecure and credential-bearing URLs',()=>{
 for(const value of ['javascript:alert(1)','data:text/html,bad','http://example.com','//example.com','https://u:p@example.com','https://example.com/\nfoo'])assert.equal(publicHttpsUrl(value),null);
 assert.equal(publicHttpsUrl('https://example.com/book?q=1'),'https://example.com/book?q=1');
});
test('public content escapes markup and omits unsafe image and booking sources',()=>{
 const html=renderToStaticMarkup(scope.exports.PersonalPage({site:{...site,photo_url:'data:image/svg+xml,bad',calendar_link:'javascript:alert(1)'}}));
 assert.ok(html.includes('&lt;script&gt;'));assert.ok(!html.includes('<script>'));assert.ok(!html.includes('javascript:'));assert.ok(!html.includes('src='));assert.ok(!html.includes('href='));
});
test('real featured values render without manufacturing a missing price',()=>{
 const html=renderToStaticMarkup(scope.exports.PersonalPage({site:{...site,featured_vehicles:[{id:'V1',year:2024,make:'Example',model:'Car',price:0},{id:'V2',make:'Other',price:null}]}}));
 assert.match(html,/2024 Example Car/);assert.match(html,/\$0/);assert.match(html,/Contact for pricing/);
});
test('personal routes are reachable in apps but remain outside marketing and Hub',()=>{
 assert.equal(deploymentRedirect('apps','/rep/fixture'),null);
 assert.equal(deploymentRedirect('apps','/rep-other'),'/apps');
 assert.equal(deploymentRedirect('marketing','/rep/fixture'),'/');
 assert.equal(deploymentRedirect('hub','/rep/fixture'),'/hub-console');
});

test('parent OEM branding renders safe logo and escaped name',()=>{
 const html=renderToStaticMarkup(scope.exports.PersonalPage({site:{...site,branding:{branding_mode:'oem',oem_name:'<Example>',oem_logo_url:'https://example.com/logo.png'}}}));
 assert.match(html,/Dealership website branding/);assert.match(html,/&lt;Example&gt;/);assert.match(html,/src="https:\/\/example.com\/logo.png"/);assert.match(html,/referrerPolicy="no-referrer"/);
});

test('independent branding ignores stale OEM fields and missing branding renders normally',()=>{
 for(const branding of [undefined,{}, {branding_mode:'independent',oem_name:'Stale manufacturer',oem_logo_url:'https://example.com/stale.png'}]){
  const html=renderToStaticMarkup(scope.exports.PersonalPage({site:{...site,branding}}));
  assert.doesNotMatch(html,/Dealership website branding|Stale manufacturer|stale.png/);
 }
});

test('unsafe or malformed branding logo never becomes an image source',()=>{
 for(const oem_logo_url of ['javascript:alert(1)','data:image/svg+xml,bad','http://example.com/logo','https://user:secret@example.com/logo',{},null]){
  const html=renderToStaticMarkup(scope.exports.PersonalPage({site:{...site,branding:{branding_mode:'oem',oem_name:'Example',oem_logo_url}}}));
  assert.doesNotMatch(html,/src=|secret|javascript:/);assert.match(html,/Example/);
 }
 const html=renderToStaticMarkup(scope.exports.PersonalPage({site:{...site,branding:{branding_mode:'oem',oem_name:{},oem_logo_url:null}}}));
 assert.doesNotMatch(html,/Dealership website branding/);
});

test('review destination is optional, external and safely rendered without invented ratings',()=>{
 const render=review_link=>renderToStaticMarkup(scope.exports.PersonalPage({site:{...site,review_link}}));
 for(const link of [undefined,null,'','javascript:alert(1)','http://example.com','https://u:p@example.com'])assert.doesNotMatch(render(link),/Leave a review/);
 const html=render('https://example.com/review');
 assert.match(html,/href="https:\/\/example.com\/review"/);
 assert.match(html,/Leave a review/);assert.match(html,/Opens an external review site/);
 assert.match(html,/noopener noreferrer/);assert.doesNotMatch(html,/rating|stars|review count/i);
});
