import assert from "node:assert/strict";
import fs from "node:fs";
import B from "../lib/forecourtBattle.js";
const context=JSON.parse(fs.readFileSync(new URL("../../backend/core/dealership_lab/catalog.json",import.meta.url)));
const cards=context.cards,starter=['host','caller','analyst'].map(id=>cards.find(c=>c.id===id));
let b=B.start(starter,'lead-rush');const original=JSON.stringify(b);let c=B.act(b,{kind:'trust'},()=>.5);assert.equal(JSON.stringify(b),original);assert.equal(c.turns,1);assert.equal(c.team[0].stamina,2);assert.equal(c.team[1].stamina,5);
assert.throws(()=>B.act(b,{kind:'swap',index:0}));assert.throws(()=>B.act(b,{kind:'recover'}));assert.throws(()=>B.start([starter[0],starter[0],starter[1]],'lead-rush'));
b.team[0].stamina=0;assert.throws(()=>B.act(b,{kind:'signature'}));b.team[0].stamina=4;
let guard=B.act(b,{kind:'guard'},()=>.5);assert.equal(guard.team[0].stamina,5);assert.ok(guard.team[0].hp>c.team[0].hp);
let swap=B.act(b,{kind:'swap',index:1},()=>.5);assert.equal(swap.active,1);assert.equal(swap.team[0].hp,b.team[0].hp);assert.equal(swap.turns,1);
let exposed=B.act(b,{kind:'insight'},()=>.5);assert.equal(exposed.foes[0].exposed.owner,'host');exposed=B.act(exposed,{kind:'swap',index:1},()=>.5);assert.equal(exposed.foes[0].exposed.ttl,1);const boosted=B.preview(exposed,'execution').damage;let plain=JSON.parse(JSON.stringify(exposed));plain.foes[0].exposed=null;assert.ok(boosted>B.preview(plain,'execution').damage);
let shield=B.start(starter,'lead-rush');shield.foes[0].shield=true;let noShield=JSON.parse(JSON.stringify(shield));noShield.foes[0].shield=false;assert.equal(B.preview(shield,'insight').damage,B.preview(noShield,'insight').damage);assert.ok(B.preview(shield,'execution').damage<B.preview(noShield,'execution').damage);
let repeated=B.start(starter,'lead-rush');const initial=B.preview(repeated,'execution').damage;repeated=B.act(repeated,{kind:'execution'},()=>.5);assert.ok(B.preview(repeated,'execution').damage<initial*.6);
let win=B.start(starter,'lead-rush');win.enemy=2;win.foes[2].hp=1;const hp=win.team[0].hp;win=B.act(win,{kind:'execution'},()=>.5);assert.equal(win.status,'won');assert.equal(win.team[0].hp,hp);assert.throws(()=>B.act(win,{kind:'guard'}));
let loss=B.start(starter,'lead-rush');loss.team.forEach(x=>x.hp=1);while(loss.status==='playing')loss=B.act(loss,{kind:'guard'},()=>.5);assert.equal(loss.status,'lost');
let timer=B.start(starter,'month-end');timer.team.forEach(x=>{x.hp=10000;x.max=10000});while(timer.status==='playing')timer=B.act(timer,{kind:'guard'},()=>.5);assert.equal(timer.status,'lost');assert.equal(timer.turns,36);
let practice=B.start(starter,'lead-rush',undefined,true);practice=B.act(practice,{kind:'guard'},()=>.5);assert.equal(practice.tutorial,0);practice=B.act(practice,{kind:'insight'},()=>.5);assert.equal(practice.tutorial,1);
for(const card of cards){const deck=[card,...starter.filter(c=>c.id!==card.id)].slice(0,3);let s=B.start(deck,'lead-rush');s.foes[0].hp=500;s.foes[0].max=500;const next=B.act(s,{kind:'signature'},()=>.5);assert.equal(next.team[0].cooldown,3);assert.match(B.blocked(next,'signature'),/stamina|ready/);assert.equal(B.skill(card).length,3);}
for(const id of ['lead-rush','aged-stock','service-peak','month-end']){const all=B.roster(id);assert.equal(all.length,9);assert.equal(new Set(all.map(f=>f.id)).size,9);for(const n of [0,.34,.99]){const foes=B.draw(id,()=>n);assert.deepEqual(foes.map(f=>f.type),['Customer','Rogue employee','Circumstance']);assert.deepEqual(B.start(starter,id,foes.map(f=>f.id)).foes.map(f=>f.id),foes.map(f=>f.id));}}
assert.throws(()=>B.start(starter,'lead-rush',['ghost','ghost','inbox']));
function legal(b){return [...Object.keys(B.moves).filter(k=>!B.blocked(b,k)).map(kind=>({kind})),...b.team.map((c,index)=>({c,index})).filter(x=>x.index!==b.active&&x.c.hp>0).map(({index})=>({kind:'swap',index}))];}
function score(b){if(b.status==='won')return 10000;if(b.status==='lost')return -10000;return b.enemy*90+(b.foes[b.enemy].max-b.foes[b.enemy].hp)+b.team.reduce((s,c)=>s+c.hp*.85+(c.hp>0?12:0)+c.stamina*1.4,0)-b.turns*1.2+(b.foes[b.enemy].exposed?5:0);}
function smart(b){let best=-Infinity,move;for(const a of legal(b)){const n=B.act(b,a,()=>.5);let val=score(n);if(n.status==='playing')val=Math.max(...legal(n).map(x=>score(B.act(n,x,()=>.5))));if(val>best){best=val;move=a;}}return move;}
function run(deck,id,policy,seed){let s=seed;const rng=()=>((s=(s*1664525+1013904223)>>>0)/4294967296);let b=B.start(deck,id,B.draw(id,rng).map(x=>x.id));while(b.status==='playing')b=B.act(b,policy(b,rng),rng);return b;}
const random=(b,r)=>{const a=legal(b);return a[Math.floor(r()*a.length)]};const spam=(b)=>!B.blocked(b,'execution')?{kind:'execution'}:{kind:'guard'};
const counts=[smart,random,spam].map(p=>Array.from({length:40},(_,i)=>run(starter,'lead-rush',p,i+1)).filter(x=>x.status==='won').length);assert.ok(counts[0]>=30);assert.ok(counts[1]<counts[0]/2);assert.ok(counts[2]<counts[0]/2);
const expert=['host','principal','finance'].map(id=>cards.find(c=>c.id===id));const results=Array.from({length:30},(_,i)=>run(expert,'month-end',smart,i+1));assert.ok(results.some(x=>x.status==='won'));assert.ok(results.some(x=>x.status==='lost'));
console.log('Turn, stamina, switching, combo, shield, signature, tutorial, loss and roster checks passed. Intro smart/random/repeated wins out of 40:',counts,'; Expert wins:',results.filter(x=>x.status==='won').length+'/30.');

// Every possible authored lineup receives the matching cast and a useful lesson.
for(const id of ['lead-rush','aged-stock','service-peak','month-end']){
 const roster=B.roster(id),groups=['Customer','Rogue employee','Circumstance'].map(type=>roster.filter(f=>f.type===type));
 for(const a of groups[0])for(const b of groups[1])for(const c of groups[2]){
  const foes=[a,b,c],brief=B.briefing(id,foes,starter);
  assert.deepEqual(brief.cast.map(x=>x.name),foes.map(x=>x.name));
  assert.deepEqual(brief.cast.map(x=>x.motive),foes.map(x=>x.story));
  assert.equal(brief.crew.length,3);assert.ok(brief.crew.every(x=>x.job&&x.contribution));
  for(const key of ['title','scene','objective','lesson','question','stakes'])assert.ok(brief[key].length>20);
 }
}
assert.notEqual(B.briefing('lead-rush',B.draw('lead-rush'),starter,true).stakes,B.briefing('lead-rush',B.draw('lead-rush'),starter).stakes);
console.log('All 108 lineup briefings and practice learning objectives passed.');
