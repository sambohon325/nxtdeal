"use client";

export function collectionPage(total: number, page: number, pageSize: number) {
  const size = Number.isFinite(pageSize) ? Math.max(1, Math.floor(pageSize)) : 25;
  const count = Number.isFinite(total) ? Math.max(0, Math.floor(total)) : 0;
  const pages = Math.max(1, Math.ceil(count / size));
  const current = Math.max(0, Math.min(Number.isFinite(page) ? Math.floor(page) : 0, pages - 1));
  return {current, pages, start: current * size, end: Math.min(count, (current + 1) * size), size};
}

/** Zero-based page contract shared by local collections and server-backed lists. */
export function CollectionPagination({total, page, pageSize = 25, onPageChange, onPageSizeChange, busy = false, label = "Records", scope = ""}: {
  total: number; page: number; pageSize?: number; onPageChange: (page: number) => void;
  onPageSizeChange?: (size: number) => void; busy?: boolean; label?: string; scope?: string;
}) {
  const p = collectionPage(total, page, pageSize);
  return <nav className="nxt-pagination" aria-label={`${label} pages`}>
    <span role="status" aria-live="polite">{total ? `${p.start + 1}–${p.end}` : "0"} of {total.toLocaleString()} {scope && `${scope} `}{label.toLowerCase()}</span>
    {onPageSizeChange && <label>Rows per page<select aria-label={`${label} rows per page`} value={p.size} disabled={busy} onChange={e => {onPageSizeChange(Number(e.target.value)); onPageChange(0);}}>{Array.from(new Set([10,25,50,p.size])).sort((a,b)=>a-b).map(n=><option key={n} value={n}>{n}</option>)}</select></label>}
    <div className="nxt-page-controls"><button className="work-button" type="button" disabled={busy || p.current === 0} onClick={()=>onPageChange(0)} aria-label={`${label}: first page`}>First</button><button className="work-button" type="button" disabled={busy || p.current === 0} onClick={()=>onPageChange(p.current - 1)}>Previous</button><span>Page {p.current + 1} of {p.pages}</span><button className="work-button" type="button" disabled={busy || p.current + 1 >= p.pages} onClick={()=>onPageChange(p.current + 1)}>Next</button><button className="work-button" type="button" disabled={busy || p.current + 1 >= p.pages} onClick={()=>onPageChange(p.pages - 1)} aria-label={`${label}: last page`}>Last</button></div>
  </nav>;
}
