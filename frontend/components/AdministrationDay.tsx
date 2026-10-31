"use client";
import {useState} from "react";
import {OverviewHeader} from "./DepartmentOverview";
import {WorkButton,WorkInput,WorkSection} from "./WorkspaceUi";
import {WorkField} from "./WorkField";
import {CollectionPagination,collectionPage} from "./CollectionPagination";
import {adminAreas,adminDestinations,type AdminArea} from "@/lib/administrationNavigation";
import styles from "./AdministrationDay.module.css";
export function AdministrationDay({allowed,onSelectItem}:{theme:"dark"|"light";allowed:Set<string>;onSelectItem:(key:string)=>void}) {
 const [area,setArea]=useState<AdminArea>("dealership"),[query,setQuery]=useState(""),[page,setPage]=useState(0);
 const entries=Object.entries(adminDestinations).filter(([key,item])=>key!=="overview"&&allowed.has(key)&&item.area===area&&`${item.label} ${item.description}`.toLowerCase().includes(query.toLowerCase()));
 const pagination=collectionPage(entries.length,page,8);
 return <section className={styles.workspace} aria-label="Administration work">
 <OverviewHeader department="Administration" title="Administration" description="Choose the work you own: dealership people and setup, or the systems that keep NXTDeal running."/>
 <nav className="work-actions" aria-label="Administration areas">{Object.entries(adminAreas).filter(([areaKey])=>Object.entries(adminDestinations).some(([key,item])=>item.area===areaKey&&allowed.has(key))).map(([key,item])=><WorkButton key={key} variant={area===key?"primary":"secondary"} aria-current={area===key?"page":undefined} onClick={()=>{setArea(key as AdminArea);setQuery("");setPage(0);}}>{item.label}</WorkButton>)}</nav>
 <WorkSection title={adminAreas[area].label} description={adminAreas[area].description}>
 <WorkField label="Find an administration task"><WorkInput type="search" value={query} placeholder="Search staff, connections, backups…" onChange={e=>{setQuery(e.target.value);setPage(0);}}/></WorkField>
 <div className={styles.tasks}>{entries.slice(pagination.start,pagination.end).map(([key,item])=><article key={key}><div><h3>{item.label}</h3><p>{item.description}</p><WorkButton onClick={()=>onSelectItem(key)}>Open {item.label}</WorkButton></div></article>)}</div>
 {!entries.length&&<p role="status">No matching tasks are available. Clear the search or check your permitted tools.</p>}
 <CollectionPagination label="Administration tasks" total={entries.length} page={pagination.current} pageSize={8} onPageChange={setPage}/>
 </WorkSection>
 <p className={styles.note}>Dealership administrators manage this dealership. System tools are available only to separately authorized NXTDeal system administrators. Dealer Lab is in the main department navigation; Help and Apps are in the upper-right toolbar.</p>
 </section>;
}
