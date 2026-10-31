export type LibraryPlan = {id:string;name:string;parent_id?:string|null;revision:number;archived:boolean;recovered_from?:{workspace_id:string;revision:number}};

// Navigation metadata only. Never alter immediate comparison parents or inputs.
export function planFamilies<T extends LibraryPlan>(plans:T[]):{id:string;name:string;plans:T[]}[] {
 const index=new Map(plans.map(p=>[p.id,p]));
 function root(plan:T):string {
  const seen=new Set<string>();let current=plan;
  while(true){
   if(seen.has(current.id))return [...seen].sort()[0];
   seen.add(current.id);
   const parent=current.recovered_from?.workspace_id||current.parent_id;
   if(!parent||!index.has(parent))return current.id;
   current=index.get(parent)!;
  }
 }
 const groups=new Map<string,T[]>();
 for(const plan of plans){const key=root(plan);groups.set(key,[...(groups.get(key)||[]),plan]);}
 return [...groups].map(([id,members])=>({id,name:index.get(id)?.name||"Saved plan family",plans:members}));
}

export type RunIntent = {baseline_id:string;proposed_id:string;baseline_revision:number;proposed_revision:number;months:number;seed:number;target:number};
export function filterRuns<T extends {id:string;created_at:string;currency:string;intent:RunIntent}>(runs:T[],plans:LibraryPlan[],filter:{family:string;months:string;currency:string;latest:boolean}):T[] {
 const members=filter.family?new Set(planFamilies(plans).find(f=>f.id===filter.family)?.plans.map(p=>p.id)||[]):null;
 const sorted=runs.filter(r=>(!members||members.has(r.intent.baseline_id)||members.has(r.intent.proposed_id))&&(!filter.months||String(r.intent.months)===filter.months)&&(!filter.currency||r.currency===filter.currency)).sort((a,b)=>b.created_at.localeCompare(a.created_at)||b.id.localeCompare(a.id));
 if(!filter.latest)return sorted;
 const seen=new Set<string>();
 return sorted.filter(r=>{const key=JSON.stringify([r.intent.baseline_id,r.intent.proposed_id,r.intent.months,r.currency]);if(seen.has(key))return false;seen.add(key);return true;});
}
export function revisionNotices(intent:RunIntent,plans:LibraryPlan[]):string[] {
 return ([['Starting plan',intent.baseline_id,intent.baseline_revision],['Option',intent.proposed_id,intent.proposed_revision]] as const).flatMap(([label,id,revision])=>{
  const current=plans.find(p=>p.id===id);
  if(!current)return [`${label} is unavailable. This comparison retains its saved revision ${revision}.`];
  const notices:string[]=[];
  if(current.revision!==revision)notices.push(`${label} has been revised since this run (saved r${revision}; current r${current.revision}).`);
  if(current.archived)notices.push(`${label} is archived.`);
  return notices;
 });
}
