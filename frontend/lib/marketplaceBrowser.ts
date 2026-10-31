import type {Marketplace,Listing,ListingState} from "./marketplace";
export type MarketplaceView="browse"|"installed"|"oem"|"phase2"|"partners";
export const marketplaceViews:Record<MarketplaceView,{title:string;description:string}>={
 browse:{title:"Marketplace",description:"Find tools for your dealership. Review setup requirements before adding a listing."},
 installed:{title:"Installed tools",description:"Review what has been added and what still needs a working provider connection."},
 oem:{title:"OEM programs",description:"Explore manufacturer programs and review their setup requirements."},
 phase2:{title:"Coming soon",description:"Preview planned tools. These listings are not available to install."},
 partners:{title:"Network partners",description:"Explore planned dealer playbooks and shared workflows."},
};
export const listingStateLabels:Record<ListingState,string>={available:"Not installed",installed:"Setup needed",connected:"Adapter available",coming_soon:"Coming soon"};
export function marketplaceCategories(data:Marketplace,view:MarketplaceView){
 return data.categories.filter(c=>view==="installed"?c.listings.some(l=>l.state==="installed"||l.state==="connected"):view==="browse"?c.section==="day1":view==="oem"?c.section==="oem":view==="partners"?c.id==="partners":c.section==="phase2"&&c.id!=="partners");
}
export function marketplaceRows(data:Marketplace,view:MarketplaceView,query:string,category:string,state:string){
 const q=query.trim().toLowerCase();
 return marketplaceCategories(data,view).filter(c=>!category||c.id===category).flatMap(c=>c.listings.map(listing=>({...listing,categoryName:c.name})))
 .filter(l=>(view!=="installed"||l.state==="installed"||l.state==="connected")&&(!state||l.state===state)&&(!q||`${l.name} ${l.blurb} ${l.categoryName}`.toLowerCase().includes(q)))
 .sort((a,b)=>a.name.localeCompare(b.name));
}
export function listingSetup(listing:Listing){
 if(listing.state==="coming_soon")return "Planned listing. Installation is not available yet.";
 if(listing.state==="connected")return "An adapter is available. Confirm provider credentials and test the connection before relying on it for live work.";
 if(listing.state==="installed")return "Added to this dealership. A live provider connection has not been established.";
 return "Adding this listing records your dealership’s selection. Provider setup and connection testing are separate steps.";
}
