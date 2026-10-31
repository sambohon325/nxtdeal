import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const file=new URL('../lib/dealerEmailDesigns.ts',import.meta.url);
const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText;
const scope={exports:{},URL,require:name=>JSON.parse(fs.readFileSync(new URL(name,file),'utf8'))};vm.runInNewContext(code,scope);
const {emailDesigns,initialEmail,renderDealerEmail,emailIssues}=scope.exports;
test('all twenty approved designs render distinct email-safe layouts with their real palettes',()=>{
 assert.equal(emailDesigns.length,20);const outputs=new Set();
 for(const d of emailDesigns){const c={...initialEmail(d.id),url:'https://dealer.example/inventory',address:'123 Test Street',unsubscribe:'https://dealer.example/unsubscribe'};const html=renderDealerEmail(d.id,c);outputs.add(html);assert.ok(html.includes(d.accent));assert.ok(html.includes('role="presentation"'));assert.ok(html.includes(c.image));assert.ok(!/<script|display:grid|backdrop-filter|javascript:/i.test(html));assert.equal(emailIssues(c).length,0);}
 assert.equal(outputs.size,20);
});
test('unsafe URLs and authored markup cannot introduce active HTML',()=>{
 const c={...initialEmail(),headline:'<img src=x onerror="alert(1)">',url:'javascript:alert(1)',image:'data:text/html,bad',unsubscribe:'https://user:secret@example.test'};
 const html=renderDealerEmail('lone-star',c);assert.ok(html.includes('&lt;img'));assert.ok(!html.includes('href="javascript:'));assert.ok(!html.includes('src="data:'));assert.ok(!html.includes('user:secret'));assert.ok(emailIssues(c).length>=2);
});
test('copy survives switching designs and unknown designs fail closed',()=>{
 const c={...initialEmail(),headline:'My dealer message',body:'One\nTwo'};
 assert.ok(renderDealerEmail('tempo',c).includes('My dealer message'));assert.ok(renderDealerEmail('tempo',c).includes('One<br/>Two'));assert.throws(()=>renderDealerEmail('unknown',c));
});

const campaignFile=new URL('../lib/dealerEmailCampaigns.ts',import.meta.url);
const campaignScope={exports:{},require:name=>name.endsWith('.json')?JSON.parse(fs.readFileSync(new URL(name,campaignFile),'utf8')):scope.exports};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(campaignFile,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,campaignScope);
test('all 60 occasions render in every design in English and Spanish',()=>{
 const {emailCampaigns,campaignEmail}=campaignScope.exports;
 assert.equal(emailCampaigns.length,60);assert.equal(new Set(emailCampaigns.map(c=>c.id)).size,60);
 for(const d of emailDesigns)for(const c of emailCampaigns)for(const lang of ['en','es']){
  const copy=campaignEmail(d.id,c.id,lang);const html=renderDealerEmail(d.id,copy);
  assert.ok(copy.body&&copy.headline&&copy.button);assert.ok(html.includes(d.accent));assert.ok(!html.includes('undefined'));assert.ok(!html.includes('�'));
  if(c.image)assert.ok(fs.existsSync(new URL('../public'+c.image,import.meta.url)));
 }
 const halloween=emailCampaigns.find(c=>c.id==='halloween');assert.ok(halloween.image.includes('halloween'));
 const es=campaignEmail('lone-star','service-due','es');es.unsubscribe='https://example.com/unsubscribe';assert.ok(renderDealerEmail('lone-star',es).includes('cancelar la suscripción'));
});
