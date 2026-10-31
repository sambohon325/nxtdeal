/* Pure turn-based rules. Game resolve/stamina are fictional, never dealership metrics. */
const ForecourtBattle=(()=>{
 const foes={
  'lead-rush':[
   ['ghost','The Ghosting Shopper','Customer','◇',28,7,2,'BDC','Calls unanswered. Earn a clear next step.',['pressure','pressure','recover']],
   ['shortcut','Shortcut Sam','Rogue employee','⚑',32,8,0,'Leadership','Skipping the CRM creates handoff gaps.',['pressure','break','pressure']],
   ['inbox','Inbox Avalanche','Circumstance','▤',38,9,1,'BDC','New leads arrive faster than the team responds.',['pressure','break','recover']]],
  'aged-stock':[
   ['bargain','The Price Challenger','Customer','◇',34,9,2,'Sales','Every offer is compared against another store.',['pressure','recover','break']],
   ['pack','Pack-it-on Pat','Rogue employee','⚑',38,10,0,'Finance','Hidden cost assumptions cloud the pricing plan.',['break','pressure','pressure']],
   ['aged','The Aging Lot','Circumstance','◷',45,11,0,'Sales','Holding costs keep building while units sit.',['pressure','break','recover']]],
  'service-peak':[
   ['walkin','The Urgent Walk-in','Customer','◇',38,10,2,'Service','An urgent request collides with a full schedule.',['pressure','pressure','break']],
   ['overbook','Overbooking Ollie','Rogue employee','⚑',43,11,0,'Leadership','Promises exceed available productive hours.',['recover','break','pressure']],
   ['bay','Bay Breakdown','Circumstance','⚙',50,12,1,'Service','A bay goes offline at the busiest moment.',['break','pressure','recover']]],
  'month-end':[
   ['terms','The Terms Challenger','Customer','◇',40,11,2,'Finance','The buyer wants a clearer explanation of the numbers.',['pressure','recover','break']],
   ['silo','Silo Strategist','Rogue employee','⚑',46,12,0,'Leadership','One department protects its numbers at everyone else’s expense.',['break','pressure','recover']],
   ['cash','Cash-flow Crunch','Circumstance','▥',54,13,0,'Finance','Timing gaps put pressure on the whole store.',['pressure','break','pressure']]]
 };
 const extra={
 'lead-rush':[
 ['comparison','Comparison Casey','Customer','◇',30,7,0,'Sales','Arrives with five competing offers.',['pressure','fortify','pressure']],
 ['lastminute','Last-minute Lee','Customer','◇',26,9,1,'BDC','Changes appointment plans at the last minute.',['drain','pressure','recover']],
 ['doublebook','Double-booking Drew','Rogue employee','⚑',30,9,1,'BDC','Assigns the same lead to multiple people.',['drain','pressure','break']],
 ['script','Script-only Sky','Rogue employee','⚑',35,7,2,'Leadership','Keeps repeating the script instead of listening.',['fortify','pressure','recover']],
 ['outage','CRM Outage','Circumstance','⚙',34,10,0,'BDC','The handoff queue disappears during peak demand.',['drain','break','recover']],
 ['surge','Weekend Ad Surge','Circumstance','▤',42,8,1,'Marketing','A campaign floods the inbox with mixed-quality leads.',['pressure','pressure','fortify']]],
 'aged-stock':[
 ['trade','Trade-value Taylor','Customer','◇',37,9,0,'Sales','An optimistic trade valuation complicates the deal.',['fortify','pressure','break']],
 ['research','Research Rabbit Hole','Customer','◇',32,10,2,'Marketing','Every answer prompts another round of comparisons.',['drain','recover','pressure']],
 ['hold','Hold-it Henry','Rogue employee','⚑',42,9,0,'Sales','Refuses to reconsider a stale price.',['fortify','pressure','fortify']],
 ['appraisal','Appraisal Ace-in-a-rush','Rogue employee','⚑',34,11,1,'Finance','Misses costs while rushing trade appraisals.',['break','drain','pressure']],
 ['transport','Transport Delay','Circumstance','◷',43,11,1,'Sales','Fresh stock is stuck on a transporter.',['drain','pressure','break']],
 ['market','Market-price Slide','Circumstance','▥',47,10,0,'Marketing','Comparable listings move down overnight.',['fortify','break','pressure']]],
 'service-peak':[
 ['callback','Comeback Cameron','Customer','◇',42,10,2,'Service','A repeat repair needs careful explanation and action.',['break','recover','pressure']],
 ['waiter','Waiting-room Wren','Customer','◇',35,12,1,'BDC','Needs a clear update before another delay.',['drain','pressure','break']],
 ['parts','Parts-hoarding Parker','Rogue employee','⚑',45,10,0,'Service','Holds parts that other jobs urgently need.',['fortify','drain','pressure']],
 ['handoff','Handoff Houdini','Rogue employee','⚑',39,12,2,'Leadership','Leaves the next shift without repair notes.',['drain','break','recover']],
 ['backorder','Backorder Blizzard','Circumstance','⚙',53,11,0,'Service','Critical parts are unavailable.',['fortify','pressure','break']],
 ['absence','Staffing Squeeze','Circumstance','◷',46,13,1,'Leadership','Several unexpected absences leave gaps in coverage.',['drain','break','pressure']]],
 'month-end':[
 ['paperwork','Paperwork Puzzle','Customer','◇',43,10,0,'Finance','Missing documents hold up completion.',['fortify','drain','pressure']],
 ['hesitation','Decision-day Devon','Customer','◇',38,12,2,'Sales','Wants reassurance before committing to the deal.',['recover','pressure','break']],
 ['spreadsheet','Spreadsheet Shadow','Rogue employee','⚑',48,11,0,'Finance','A private spreadsheet disagrees with the shared totals.',['fortify','drain','break']],
 ['promise','Overpromise Morgan','Rogue employee','⚑',42,13,2,'Leadership','Commits the store to plans before checking capacity.',['break','pressure','drain']],
 ['reconcile','Reconciliation Rift','Circumstance','▥',56,12,0,'Finance','Two reporting sources no longer agree.',['fortify','break','recover']],
 ['deadline','Deadline Domino','Circumstance','◷',50,14,1,'Leadership','Several time-sensitive obligations collide.',['drain','pressure','break']]]};

 const names=['Insight','Execution','Trust'];
 const moves={insight:{name:'Spot the loophole',stat:0,cost:2},execution:{name:'Make it happen',stat:1,cost:2},trust:{name:'Talk them down',stat:2,cost:2},signature:{name:'Signature move',cost:3},guard:{name:'Brace & recharge',cost:0},recover:{name:'Catch your breath',cost:3}};
 const skills={host:['Warm welcome','trust','Soften the next attack and restore 8 resolve.'],caller:['Perfect handoff','insight','Expose the opponent and give your bench +1 stamina.'],analyst:['Read the fine print','insight','Break shields and expose the opponent.'],principal:['Manager override','trust','Cancel the opponent’s next action.'],inventory:['Price drop','execution','Amplify handoff pressure by 50% against an exposed opponent.'],people:['Rally the crew','trust','Restore 8 resolve to every standing teammate.'],service:['Safety first','execution','Protect the whole crew from the next two attacks.'],systems:['Reboot the queue','insight','Break shields and give every standing teammate +1 stamina.'],marketing:['Change the conversation','trust','Expose the opponent and soften their next attack.'],technician:['First-time fix','execution','Ignore resistance and shields.'],finance:['No hidden fees','trust','Stop the next recovery or fortification; soften their next attack.'],champion:['All hands on deck','execution','Expose the opponent and restore 6 resolve to the crew.']};
 function skill(c){return skills[c.id]||skills.host;}
 function enemies(id){if(!foes[id])throw Error('Choose a battle.');const scale={'lead-rush':[1.45,1.3],'aged-stock':[1.65,1.4],'service-peak':[1.75,1.45],'month-end':[1.85,1.5]}[id];return foes[id].map(([id,name,type,icon,hp,power,weak,dept,story,pattern])=>({id,name,type,icon,hp:Math.round(hp*scale[0]),max:Math.round(hp*scale[0]),power:Math.round(power*scale[1]),weak,dept,story,pattern}));}
 function roster(id){const first=enemies(id),scale={'lead-rush':[1.45,1.3],'aged-stock':[1.65,1.4],'service-peak':[1.75,1.45],'month-end':[1.85,1.5]}[id];return first.concat(extra[id].map(([id,name,type,icon,hp,power,weak,dept,story,pattern])=>({id,name,type,icon,hp:Math.round(hp*scale[0]),max:Math.round(hp*scale[0]),power:Math.round(power*scale[1]),weak,dept,story,pattern})));}
 function draw(id,rng=Math.random){const all=roster(id);return ['Customer','Rogue employee','Circumstance'].map(type=>{const group=all.filter(f=>f.type===type);return group[Math.min(group.length-1,Math.floor(rng()*group.length))];});}
 const shiftBriefs={
  'lead-rush':{title:'Monday: the CRM has entered the chat',scene:'The weekend campaign worked. Unfortunately, so did everyone’s snooze button. Shoppers need a clear next step while the team tries to keep the queue moving.',objective:'Recover the handoffs and clear all three disruptions before the shift ends.',lesson:'Lead volume is only useful when someone owns the next action. Capacity, follow-up and a clear handoff need to work together.',question:'In your dealership model, would another campaign help—or would response coverage be the better first test?'},
  'aged-stock':{title:'The lot that time forgot',scene:'A row of vehicles is applying for permanent residency. Customers challenge the prices, internal assumptions muddy the numbers, and the clock keeps charging rent.',objective:'Resolve the pricing objections, untangle the process problem and get the inventory plan moving.',lesson:'A bigger discount can improve turn while sacrificing gross. Compare acquisition cost, recon, holding cost and total contribution together.',question:'Which saved scenario improves inventory movement without quietly giving away the margin?'},
  'service-peak':{title:'Tuesday: everybody needs it by lunch',scene:'The appointment board is full, the coffee is empty, and “just squeeze one more in” has become a scheduling strategy. Your crew must protect the workflow.',objective:'Handle the customer concern, fix the team handoff and remove the capacity disruption.',lesson:'More bookings do not create more productive hours. Check advisor coverage, technician availability, parts and bays before promising extra work.',question:'Which constraint would your service simulation hit first if bookings rose by 25%?'},
  'month-end':{title:'Month-end: the spreadsheet strikes back',scene:'The sales board looks heroic. The cash balance would like a word. Competing priorities and incomplete explanations threaten to turn the close into an all-nighter.',objective:'Clarify the deal, align the departments and resolve the final financial disruption.',lesson:'Sales, gross, profit and cash are different measures. Reconcile assumptions and payment timing before celebrating a result.',question:'Does your proposed plan improve cash as well as profit—and what evidence would confirm it?'}
 };
 function briefing(id,lineup,team=[],practice=false){
  if(!shiftBriefs[id])throw Error('Choose a battle.');
  const base=shiftBriefs[id];return {...base,objective:practice?'Practice an Insight setup, switch specialists, then use the opening. Resolve this one opponent.':base.objective,
   cast:lineup.map(f=>({name:f.name,role:f.type,motive:f.story,approach:names[f.weak],department:f.dept})),
   crew:team.map(c=>({name:c.name,job:c.job||c.dept,contribution:skill(c)[2]})),
   stakes:practice?'A rehearsal, not a scored shift. No collection reward.':'Win by resolving all three opponent cards within 36 turns. Lose if the whole crew is exhausted or time runs out.'};
 }
 function start(cards,id,lineup,practice=false){
  if(cards.length!==3||new Set(cards.map(c=>c.id)).size!==3||cards.some(c=>!skills[c.id])||cards.reduce((s,c)=>s+c.cost,0)>8)throw Error('Choose three different collected cards using at most 8 team points.');
  let opponents=enemies(id);if(lineup){const all=roster(id);if(lineup.length!==3||new Set(lineup).size!==3)throw Error('Choose a valid opponent lineup.');opponents=lineup.map(i=>all.find(f=>f.id===i));if(opponents.some((f,i)=>!f||f.type!==['Customer','Rogue employee','Circumstance'][i]))throw Error('Invalid opponent combination.');}
  opponents=JSON.parse(JSON.stringify(opponents));if(practice)opponents=opponents.slice(0,1).map(f=>({...f,hp:85,max:85,power:3,weak:1}));
  return {version:2,id,practice,tutorial:0,round:1,turns:0,status:'playing',active:0,enemy:0,last:null,repeat:0,guardChain:0,cover:0,team:cards.map(c=>({...c,hp:38+c.stats[2]*2,max:38+c.stats[2]*2,stamina:4,cooldown:0})),foes:opponents.map(f=>({...f,step:0,exposed:null,soft:false,shield:false,heals:0})),log:[practice?'Practice: try a setup, switch, then cash in the opening. No collection rewards.':'The shift begins. Resolve three opponents before turn 36. Your crew has separate stamina.']};
 }
 function intent(b){const f=b.foes[b.enemy];if(b.repeat>=2)return 'break';if(f.hp<f.max*.3&&f.heals<1)return 'recover';return f.pattern[f.step%f.pattern.length];}
 function cost(b,kind){return moves[kind]?.cost??0;}
 function blocked(b,kind){const c=b.team[b.active],m=moves[kind];if(b.status!=='playing')return 'Battle finished';if(!m)return 'Unknown move';if(c.stamina<m.cost)return 'Not enough stamina — switch or recharge';if(kind==='signature'&&c.cooldown)return `Signature ready in ${c.cooldown} turns`;if(kind==='recover'&&c.hp===c.max)return 'Already at full resolve';return '';}
 function preview(b,kind){const c=b.team[b.active],f=b.foes[b.enemy],m=moves[kind];if(m.stat===undefined&&kind!=='signature')return {damage:0,notes:kind==='guard'?'Block 65% and gain 2 stamina. Repeated bracing only blocks 20%.':'Restore 16 resolve; your opponent still acts.'};
  const sig=kind==='signature',stat=sig?names.map(n=>n.toLowerCase()).indexOf(skill(c)[1]):m.stat;
  let damage=4+c.stats[stat]*1.4+(sig?5:0),notes=[];
  const pierce=sig&&['technician','analyst','systems'].includes(c.id);
  if(stat===f.weak){damage*=1.65;notes.push('Weakness ×1.65');}else if(stat===(f.weak+1)%3&&!pierce){damage*=.5;notes.push('Resisted ×0.5');}
  if(c.dept===f.dept){damage+=5;notes.push('Department +5');}
  if(f.exposed&&f.exposed.owner!==c.id){damage+=12;notes.push('Handoff +12');if(sig&&c.id==='inventory')damage*=1.5;}
  if(b.last?.id===c.id&&b.last.kind===kind){damage*=.45;notes.push('Predictable ×0.45');}
  if(f.shield&&!pierce&&kind!=='insight'){damage*=.35;notes.push('Shield ×0.35');}
  return {damage:Math.max(1,Math.round(damage)),notes:notes.join(' · ')||'Normal effectiveness'};
 }
 function act(input,action,rng=Math.random){
  const b=JSON.parse(JSON.stringify(input));if(b.status!=='playing')throw Error('This battle is finished.');let c=b.team[b.active],f=b.foes[b.enemy],guard=1,skip=false;const impending=intent(b),lines=[];const add=t=>lines.push(t);const heal=(x,n)=>{const h=Math.min(x.max-x.hp,n);if(x.hp>0)x.hp+=h;return h;};
  if(action.kind==='swap'){if(!Number.isInteger(action.index)||action.index===b.active||!b.team[action.index]||b.team[action.index].hp<=0)throw Error('Choose another ready specialist.');b.active=action.index;c=b.team[b.active];guard=.55;b.guardChain=0;b.repeat=0;add(`${c.name} tags in: blocks 45% this turn. The bench recovers stamina.`);}
  else{const reason=blocked(b,action.kind);if(reason)throw Error(reason);const estimate=preview(b,action.kind);c.stamina-=cost(b,action.kind);
   if(action.kind==='guard'){guard=b.guardChain ? .8 : .35;b.guardChain++;c.stamina=Math.min(5,c.stamina+2);b.repeat=0;add(`${c.name} recharges +2 stamina; ${b.guardChain>1?'the opponent anticipated the repeated brace (20% block).':'65% block.'}`);}
   else if(action.kind==='recover'){b.guardChain=0;b.repeat=0;add(`${c.name} catches a breath: +${heal(c,16)} resolve. Coffee is not a strategy, but it helps.`);}
   else{b.guardChain=0;const sig=action.kind==='signature';const damage=Math.max(1,Math.round(estimate.damage*(.95+rng()*.1)));f.hp=Math.max(0,f.hp-damage);add(`${c.name} uses ${sig?skill(c)[0]:moves[action.kind].name}: ${damage} pressure. ${estimate.notes}.`);
    if(f.exposed?.owner!==c.id)f.exposed=null;
    if(action.kind==='insight'||sig&&['caller','analyst','marketing','champion'].includes(c.id)){f.exposed={owner:c.id,ttl:3};f.shield=false;add('Opening created: switch to a teammate for +12 on their next attack.');}
    if(action.kind==='trust'||sig&&['host','marketing','finance'].includes(c.id)){f.soft=true;add('Opponent softened: their next attack deals 45% less.');}
    if(sig){c.cooldown=4;switch(c.id){case 'host':heal(c,8);break;case 'people':b.team.forEach(x=>heal(x,8));break;case 'champion':b.team.forEach(x=>heal(x,6));break;case 'principal':skip=true;add('Manager override: opponent action cancelled.');break;case 'service':b.cover=2;break;case 'caller':b.team.forEach((x,i)=>{if(i!==b.active)x.stamina=Math.min(5,x.stamina+1);});break;case 'systems':f.shield=false;b.team.forEach(x=>x.stamina=Math.min(5,x.stamina+1));break;case 'analyst':f.shield=false;break;case 'finance':if(['recover','fortify'].includes(impending)){skip=true;add('No hidden fees: opponent setup cancelled.');}break;}}
    b.repeat=b.last?.id===c.id&&b.last.kind===action.kind?b.repeat+1:1;b.last={id:c.id,kind:action.kind};
   }
  }
  if(b.practice){const expected=['insight','swap','execution','guard'];if(action.kind===expected[b.tutorial||0])b.tutorial=(b.tutorial||0)+1;}
  b.turns++;f.step++;
  if(f.hp<=0){add(`${f.name} resolved. Someone finally updated the CRM.`);b.enemy++;b.repeat=0;b.last=null;if(b.enemy===b.foes.length){b.status='won';add('Shift secured! The dealership survives another perfectly normal day.');}else add(`${b.foes[b.enemy].name} arrives next turn. No free hit during the handoff.`);}
  else if(!skip){if(impending==='fortify'){f.shield=true;add(`${f.name} builds a shield: blocks 65%. Insight breaks it.`);}else if(impending==='recover'){const n=Math.min(f.max-f.hp,12);f.hp+=n;f.heals++;add(`${f.name} recovers ${n} resolve. “Just one more question…”`);}else{let hit=Math.round((f.power+(impending==='break'?8:0)+Math.floor(f.step/5)*2)*(.95+rng()*.1));if(c.dept===f.dept)hit=Math.round(hit*.8);hit=Math.ceil(hit*guard*(f.soft?.55:1)*(b.cover>0?.6:1));f.soft=false;if(b.cover>0)b.cover--;c.hp=Math.max(0,c.hp-hit);if(impending==='drain')c.stamina=Math.max(0,c.stamina-2);add(`${f.name}: ${impending==='break'?'Big disruption':impending==='drain'?'Distraction (−2 stamina)':'Pressure'} — ${hit} resolve lost.`);}}
  if(f.exposed&&--f.exposed.ttl<=0)f.exposed=null;
  b.team.forEach((x,i)=>{x.cooldown=Math.max(0,x.cooldown-1);if(i!==b.active&&x.hp>0)x.stamina=Math.min(5,x.stamina+1);});
  if(c.hp<=0){add(`${c.name} is exhausted. Their out-of-office is now on.`);const next=b.team.findIndex(x=>x.hp>0);if(next<0){b.status='lost';add('Shift lost. Try a different lineup, protect against big attacks, and use the bench.');}else{b.active=next;b.repeat=0;b.last=null;add(`${b.team[next].name} steps in.`);}}
  if(b.status==='playing'&&b.turns>=36){b.status='lost';add('The 36-turn shift is over. Too much stalling; not enough closing.');}
  b.round=b.turns+1;b.log.push(`TURN ${b.turns}`,...lines);return b;
 }
 return {enemies,roster,draw,start,act,intent,moves,names,skill,preview,blocked,cost,briefing};
})();
export default ForecourtBattle;
