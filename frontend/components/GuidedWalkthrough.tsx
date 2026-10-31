"use client";
import {useEffect,useRef,useState,type CSSProperties} from "react";
import {WorkButton} from "./WorkspaceUi";
import {departmentTourTargets} from "@/lib/departmentTourTargets";
import {helpGuides,helpGuideFor,tourSteps} from "@/lib/helpContent";
export type WalkthroughContext={department:string;title:string;welcome?:boolean;departmentTour?:boolean;isSystemAdmin?:boolean};
type Step={title:string;text:string;selector:string;action?:string;targetLabels?:string[]};
const colors=["#ffca58","#e99cff","#65e6bb","#ff9b75"];
const visible=(e:Element)=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&getComputedStyle(e).visibility!=="hidden";};
function find(selector:string){for(const part of selector.split(",")){const match=Array.from(document.querySelectorAll(part.trim())).find(visible);if(match)return match as HTMLElement;}return undefined;}
function findStepTarget(step:Step){
 for(const label of step.targetLabels||[]){
  const controls=Array.from(document.querySelectorAll('button,a,summary,[role="tab"]')).filter(e=>!e.closest('.guided-layer')&&visible(e));
  const match=controls.find(e=>(e.getAttribute('aria-label')||e.textContent||'').trim().toLowerCase()===label.toLowerCase());
  if(match)return match as HTMLElement;
 }
 return find(step.selector);
}
/** Only describe controls that actually exist. Never execute a record action for a learner. */
export function pageSteps(context:WalkthroughContext):Step[]{
 const guide=helpGuideFor(context.department,context.isSystemAdmin);
 const targets=context.department==="Administration"&&!context.isSystemAdmin?[["Dealership administration"],["Staff accounts & onboarding"],["Dealership profile & locations"],["Roles & access requests"],["Business approvals & compliance"],["Help"]]:departmentTourTargets[context.department];
 if(context.departmentTour&&guide)return guide.steps.map((text,index)=>({title:targets?.[index]?.[0]||`Step ${index+1}`,text,targetLabels:targets?.[index],selector:index===0?'#dealership-content h2, #dealership-content h1':index===guide.steps.length-1?'#dealership-content [data-record-detail], #dealership-content .work-record-content, #dealership-content h2':'#dealership-content nav[aria-label$="sections"], #dealership-content .work-toolbar, #dealership-content form, #dealership-content nav[aria-label$="daily work"], #workflow-navigation',action:index===guide.steps.length-1?guide.check:"Follow this step on the page. Use the sidebar or daily-work tabs to reach the task, then choose Next. You can minimize the guide while working."}));
 const steps:Step[]=[{title:`Start here: ${context.title}`,text:guide?.before||"Check the page title and current record before making changes.",selector:'#dealership-content h2, #dealership-content h1'}];
 const candidates:Step[]=[
  {title:"Find the right record",text:"Use this search or filter to narrow the list. Try a name, vehicle or identifier you already know. Clear the filter to see the full list again.",selector:'#dealership-content input[type="search"], #dealership-content input[placeholder*="earch"], #dealership-content select',action:"Try the highlighted search or filter, then choose Next."},
  {title:"Choose the work you need",text:"Open a record to see its details. Check the customer, vehicle or reference number so you work on the correct item.",selector:'#dealership-content tbody tr, #dealership-content [data-record-detail], #dealership-content .work-record-content',action:"Open a record if you want to follow along. Then choose Next."},
  {title:"Move through this section",text:"These tabs split the work into smaller steps. Select the part you need, review its contents, then continue. Changing a tracking stage alone does not perform the underlying work.",selector:'#dealership-content nav[aria-label$="sections"], #dealership-content [role="tablist"]',action:"Try a section tab. Your walkthrough stays open."},
  {title:"Work through the fields",text:"Read each field label and enter the details you can confirm. Required fields and validation messages tell you what is missing. Review values before saving.",selector:'#dealership-content .work-field, #dealership-content textarea, #dealership-content form',action:"You control every edit. The walkthrough never fills or submits a form."},
  {title:"Use the list controls",text:"Use Previous and Next to move through results. The count shows how many records match your filters. Changing pages does not change a record.",selector:'#dealership-content nav[aria-label$="pages"]',action:"Try another page, then return to the record you need."},
 ];
 for(const candidate of candidates)if(find(candidate.selector))steps.push(candidate);
 if(steps.length===1)steps.push({title:"Choose your next task",text:guide?.steps[0]||"Choose a daily-work shortcut or open a group in the left navigation.",selector:'#dealership-content nav[aria-label$="daily work"], #workflow-navigation',action:"Choose a task on the page, then use Next to continue the walkthrough."});
 steps.push({title:"Check the result and next owner",text:guide?.check||"Confirm the saved result and leave a clear next action for the person continuing the work.",selector:'#dealership-content',action:"Save only when you intend to make the change. If saving fails, keep the form open and read the error."});
 return steps;
}
export function GuidedWalkthrough({context,onClose,onHelp}:{context:WalkthroughContext;onClose:()=>void;onHelp:()=>void}){
 const [steps,setSteps]=useState<Step[]>([]),[index,setIndex]=useState(0),[rect,setRect]=useState<{left:number;top:number;width:number;height:number}|null>(null),[minimized,setMinimized]=useState(false);
 const card=useRef<HTMLElement>(null);const current=steps[index];
 useEffect(()=>{card.current?.focus();},[steps]);
 useEffect(()=>{const previous=document.activeElement as HTMLElement|null;setSteps(context.welcome?tourSteps.map(s=>({title:s.title,text:s.text,selector:s.target})):pageSteps(context));card.current?.focus();return()=>{if(previous?.isConnected)previous.focus();};},[context]);
 useEffect(()=>{const escape=(e:KeyboardEvent)=>{if(e.key==="Escape")onClose();};window.addEventListener('keydown',escape);return()=>window.removeEventListener('keydown',escape);},[onClose]);
 useEffect(()=>{
  if(!current)return;let frame=0;let last:HTMLElement|undefined;
  const update=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{const target=findStepTarget(current);if(target!==last){last=target;target?.scrollIntoView({block:"start",behavior:"auto"});}if(!target){setRect(null);return;}const r=target.getBoundingClientRect();const left=Math.max(6,r.left-5),top=Math.max(6,r.top-5);setRect({left,top,width:Math.max(0,Math.min(r.right+5,innerWidth-6)-left),height:Math.max(0,Math.min(r.bottom+5,innerHeight-6)-top)});});};
  update();window.addEventListener('resize',update);window.addEventListener('scroll',update,true);const observer=new MutationObserver(records=>{if(records.some(record=>!(record.target as Element).closest?.('.guided-layer')))update();});observer.observe(document.getElementById('dealership-content')||document.body,{childList:true,subtree:true});
  return()=>{cancelAnimationFrame(frame);observer.disconnect();window.removeEventListener('resize',update);window.removeEventListener('scroll',update,true);};
 },[current]);
 function next(){if(index===steps.length-1){onClose();return;}setIndex(v=>v+1);}
 if(!current)return null;
 return <div className="guided-layer" style={{'--tour-accent':colors[index%colors.length]} as CSSProperties}>
 {rect&&!minimized&&<div className="guided-highlight" style={rect} aria-hidden="true"><span>Step {index+1}</span></div>}
 <section ref={card} tabIndex={-1} role="region" aria-label="Guided walkthrough" style={rect&&innerWidth>900&&rect.left>innerWidth/2?{left:24,right:"auto"}:undefined} className={`guided-card ${minimized?'guided-minimized':''}`}>
 <header><span className="guided-kicker">{context.welcome?"Welcome tour":context.department==="Network"?"Dealer Lab walkthrough":`${context.department} walkthrough`}</span><button onClick={onClose} aria-label="Close walkthrough">×</button></header>
 <div className="guided-progress" aria-label={`Step ${index+1} of ${steps.length}`}>{steps.map((s,i)=><button key={`${i}:${s.title}`} aria-label={`Go to step ${i+1}: ${s.title}`} aria-current={i===index?'step':undefined} onClick={()=>setIndex(i)} />)}</div>
 <h2 aria-live="polite">{current.title}</h2>
 {!minimized&&<><p>{current.text}</p>{current.action&&<p className="guided-action">{current.action}</p>}{!rect&&<p className="guided-action">This control is not visible in the current view. You can continue, or open Help again to guide the page you are on.</p>}</>}
 <div className="work-actions"><WorkButton onClick={()=>setMinimized(v=>!v)}>{minimized?'Expand guide':'Minimize'}</WorkButton><WorkButton disabled={index===0} onClick={()=>setIndex(v=>v-1)}>Back</WorkButton><WorkButton variant="primary" onClick={next}>{index===steps.length-1?'Finish':'Next'}</WorkButton></div>
 {!minimized&&<footer><span>{index+1} / {steps.length} · You can use the page while this guide is open.</span><button onClick={()=>{setSteps(pageSteps({...context,departmentTour:false,title:find("#dealership-content h2")?.textContent||context.title}));setIndex(0);}}>Guide the current screen</button><button onClick={onHelp}>Read the guide</button></footer>}
 </section></div>;
}
export function ContextHelp({department,title,onWalkthrough,onLibrary,onClose}:{department:string;title:string;onWalkthrough:()=>void;onLibrary:()=>void;onClose:()=>void}){
 const ref=useRef<HTMLDialogElement>(null);useEffect(()=>{const dialog=ref.current;dialog?.showModal();return()=>dialog?.close();},[]);
 return <dialog ref={ref} className="nxt-utility-dialog nxt-workspace-content context-help" aria-labelledby="context-help-title" onCancel={onClose}><header><div><p className="help-muted">{department} · Help for this page</p><h2 id="context-help-title">{title}</h2></div><WorkButton onClick={onClose}>Close</WorkButton></header><p>Follow a guided walkthrough on this screen, or read a short department guide.</p><div className="help-choice"><WorkButton variant="primary" onClick={onWalkthrough}>Walk me through this page</WorkButton><WorkButton onClick={onLibrary}>Browse Help & learning</WorkButton></div><p className="help-muted">Your current screen and unsaved work stay in place during the walkthrough.</p></dialog>;
}

