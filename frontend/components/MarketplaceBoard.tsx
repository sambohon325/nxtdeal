"use client";
import {useEffect,useRef,useState} from "react";
import {WorkButton,WorkInput,WorkSelect,WorkSection,WorkEmpty,WorkStat,WorkToolbar} from "./WorkspaceUi";
import {WorkField} from "./WorkField";
import {OverviewHeader} from "./DepartmentOverview";
import {CollectionPagination,collectionPage} from "./CollectionPagination";
import {fetchMarketplace,fetchListing,installListing,uninstallListing,type Marketplace,type ListingDetail} from "@/lib/marketplace";
import {marketplaceViews,marketplaceCategories,marketplaceRows,listingStateLabels,listingSetup,type MarketplaceView} from "@/lib/marketplaceBrowser";
import styles from "./MarketplaceBoard.module.css";
export type {MarketplaceView} from "@/lib/marketplaceBrowser";

export function MarketplaceBoard({view="browse",hideHeading=false}:{theme:"dark"|"light";view?:MarketplaceView;hideHeading?:boolean}){
 const [data,setData]=useState<Marketplace|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState("");
 const [query,setQuery]=useState(""),[category,setCategory]=useState(""),[status,setStatus]=useState(""),[page,setPage]=useState(0),[retry,setRetry]=useState(0);
 const [selected,setSelected]=useState<string|null>(null),[detail,setDetail]=useState<ListingDetail|null>(null),[detailError,setDetailError]=useState(""),[detailRetry,setDetailRetry]=useState(0);
 const [busy,setBusy]=useState(false),[notice,setNotice]=useState(""),[confirmRemove,setConfirmRemove]=useState(false);
 const heading=useRef<HTMLHeadingElement>(null),backTarget=useRef<HTMLButtonElement|null>(null),saving=useRef(false);
 const activeView=marketplaceViews[view]?view:"browse";
 useEffect(()=>{let active=true;setLoading(true);setError("");fetchMarketplace().then(value=>{if(active)setData(value);}).catch(e=>{if(active)setError(e instanceof Error?e.message:"Unable to load Marketplace.");}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[retry]);
 useEffect(()=>{setQuery("");setCategory("");setStatus("");setPage(0);setSelected(null);setNotice("");},[view]);
 useEffect(()=>{
  let active=true;setDetail(null);setDetailError("");setConfirmRemove(false);
  if(selected)fetchListing(selected).then(value=>{if(active)setDetail(value);}).catch(e=>{if(active)setDetailError(e instanceof Error?e.message:"Unable to load listing.");});
  return()=>{active=false;};
 },[selected,detailRetry]);
 useEffect(()=>{if(detail)heading.current?.focus();},[detail?.id]);
 function closeDetail(){if(busy)return;setSelected(null);setNotice("");requestAnimationFrame(()=>backTarget.current?.focus());}
 async function changeInstallation(){
  if(!detail||data?.can_manage!==true||saving.current||detail.state==="coming_soon")return;
  const remove=detail.state==="installed"||detail.state==="connected";
  if(remove&&!confirmRemove){setConfirmRemove(true);return;}
  saving.current=true;setBusy(true);setDetailError("");setNotice("");
  try{
   const updated=remove?await uninstallListing(detail.id):await installListing(detail.id);
   setDetail({...detail,...updated});setConfirmRemove(false);
   setNotice(remove?`${updated.name} removed from installed listings. Provider configuration is unchanged.`:`${updated.name} added. Review the setup status below before using it.`);
   try{setData(await fetchMarketplace());}catch{setError("The change was saved, but the catalog could not refresh. Reload the catalog to see the latest counts.");}
  }catch(e){setDetailError(e instanceof Error?e.message:"The change could not be saved. Check the listing status before trying again.");}
  finally{saving.current=false;setBusy(false);}
 }
 const info=marketplaceViews[activeView],rows=data?marketplaceRows(data,activeView,query,category,status):[],paging=collectionPage(rows.length,page,12);
 function reset(){setQuery("");setCategory("");setStatus("");setPage(0);}
 return <section className={styles.workspace} aria-label="Marketplace catalog" aria-busy={loading||busy}>
 {!hideHeading&&<OverviewHeader department="Marketplace" title={info.title} description={info.description}/>}
 {hideHeading&&<p className={styles.intro}>{info.description}</p>}
 {error&&<div role="alert"><p>{error}</p><WorkButton disabled={loading||busy} onClick={()=>setRetry(v=>v+1)}>Reload catalog</WorkButton></div>}
 {loading&&!data?<p role="status">Loading Marketplace…</p>:!data?null:selected?<>
 <div className="work-actions"><WorkButton disabled={busy} onClick={closeDetail}>Back to results</WorkButton></div>
 {notice&&<p role="status">{notice}</p>}
 {detailError&&<div role="alert"><p>{detailError}</p>{!detail&&<WorkButton onClick={()=>setDetailRetry(v=>v+1)}>Retry listing</WorkButton>}</div>}
 {!detail&&!detailError&&<p role="status">Loading listing details…</p>}
 {detail&&<article className={styles.detail} data-record-detail><header><p>{detail.category_name}</p><h3 tabIndex={-1} ref={heading}>{detail.name}</h3><span className={styles.status}>{listingStateLabels[detail.state]}</span><p>{detail.blurb}</p></header>
 <WorkSection title="What this tool is for"><ul>{detail.purpose.map(purpose=><li key={purpose}>{purpose}</li>)}</ul></WorkSection>
 <WorkSection title="Setup and availability"><p>{listingSetup(detail)}</p>{detail.installed_at&&<p>Added {new Date(detail.installed_at).toLocaleDateString()} · {detail.installed_by||"Administrator"}</p>}
 {detail.state!=="coming_soon"&&<p>Adding a listing does not purchase a vendor subscription or complete provider authorization. NXTDeal system administrators manage provider configuration.</p>}
 </WorkSection>
 {data.can_manage!==true?<p>Browse and review tools here. Contact your NXTDeal system administrator to add, configure or remove a listing.</p>:detail.state==="coming_soon"?<p>This listing cannot be installed yet.</p>:<WorkSection title={confirmRemove?"Remove this listing?":"Manage this listing"}>
 {confirmRemove&&<p>Remove {detail.name} from this dealership’s installed list. This does not disconnect its provider or cancel a vendor subscription.</p>}
 <div className="work-actions"><WorkButton variant={confirmRemove?"danger":"primary"} disabled={busy} onClick={changeInstallation}>{busy?"Saving…":confirmRemove?"Confirm removal":detail.state==="available"?"Add to dealership":"Remove listing"}</WorkButton>{confirmRemove&&<WorkButton disabled={busy} onClick={()=>setConfirmRemove(false)}>Keep listing</WorkButton>}</div>
 </WorkSection>}
 </article>}
 </>:<>
 <div className={styles.snapshot}><WorkStat label="Catalog listings" value={data.summary.total_listings}/><WorkStat label="Added to dealership" value={data.summary.installed+data.summary.connected}/><WorkStat label="Setup needed" value={data.summary.installed}/></div>
 <WorkToolbar label="Marketplace filters"><WorkField label="Search listings"><WorkInput type="search" value={query} placeholder="Search by name, purpose or category" onChange={e=>{setQuery(e.target.value);setPage(0);}}/></WorkField><WorkField label="Category"><WorkSelect value={category} onChange={e=>{setCategory(e.target.value);setPage(0);}}><option value="">All categories</option>{marketplaceCategories(data,activeView).map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</WorkSelect></WorkField><WorkField label="Status"><WorkSelect value={status} onChange={e=>{setStatus(e.target.value);setPage(0);}}><option value="">All statuses</option>{Object.entries(listingStateLabels).map(([key,label])=><option key={key} value={key}>{label}</option>)}</WorkSelect></WorkField><WorkButton disabled={!query&&!category&&!status} onClick={reset}>Clear filters</WorkButton></WorkToolbar>
 {data.can_manage!==true&&<p className={styles.intro}>You can explore every listing. NXTDeal system administrators manage installations and provider connections.</p>}
 {!rows.length?<WorkEmpty title={query||category||status?"No matching listings":"No listings in this view"} description={activeView==="installed"?"Nothing matches your installed tools. Browse Marketplace from the left navigation to find a tool.":"Try another category or clear your filters."}>{(query||category||status)&&<WorkButton onClick={reset}>Clear filters</WorkButton>}</WorkEmpty>:<div className={styles.grid}>{rows.slice(paging.start,paging.end).map(listing=><article className={styles.card} key={listing.id}><p className={styles.category}>{listing.categoryName}</p><div className={styles.cardTitle}><h3>{listing.name}</h3><span className={styles.status}>{listingStateLabels[listing.state]}</span></div><p>{listing.blurb}</p><WorkButton aria-label={`View ${listing.name} details`} onClick={event=>{backTarget.current=event.currentTarget;setSelected(listing.id);setNotice("");}}>View details</WorkButton></article>)}</div>}
 <CollectionPagination label="Marketplace listings" total={rows.length} page={paging.current} pageSize={12} onPageChange={setPage}/>
 </>}
 </section>;
}
