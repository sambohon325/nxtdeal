export type FinanceDetail={run_id?:string;replay_engine_commit?:string;compatibility?:string;basis:string;currency:string;seed:number;trial:number;shared_engine_commit:string;sides:Record<string,{monthly:Record<string,number>[];assumptions:Record<string,number>}>};

// Export server-returned paths verbatim; do not reconstruct financial outcomes.
export function financeCsv(detail:FinanceDetail,runId:string){
 const sides=Object.entries(detail.sides);
 const fields=[...new Set(sides.flatMap(([,side])=>side.monthly.flatMap(row=>Object.keys(row))))];
 const assumptions=[...new Set(sides.flatMap(([,side])=>Object.keys(side.assumptions)))];
 const quote=(value:unknown)=>{const raw=String(value??'');const safe=typeof value==='string'&&/^[=+\-@\t\r]/.test(raw)?"'"+raw:raw;return '"'+safe.replaceAll('"','""')+'"';};
 const header=['run_id','saved_engine_commit','replay_engine_commit','basis','currency','seed','trial','plan',...fields,...assumptions.map(k=>'assumption_'+k)];
 const rows=sides.flatMap(([side,data])=>data.monthly.map(row=>[
  detail.run_id||runId,detail.shared_engine_commit,detail.replay_engine_commit||detail.shared_engine_commit,detail.basis,detail.currency,detail.seed,detail.trial,side,
  ...fields.map(key=>row[key]??''),...assumptions.map(key=>data.assumptions[key]??''),
 ]));
 return [header,...rows].map(row=>row.map(quote).join(',')).join('\r\n');
}
