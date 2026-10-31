"use client";
import {Children, Fragment, cloneElement, isValidElement, useState, type ReactElement, type ReactNode, type TableHTMLAttributes} from "react";
import {CollectionPagination, collectionPage} from "./CollectionPagination";

function flatten(nodes: ReactNode): ReactNode[] {
  return Children.toArray(nodes).flatMap(node => isValidElement<{children?:ReactNode}>(node) && node.type === Fragment ? flatten(node.props.children) : [node]);
}

/** Keeps the actual row controls and table semantics; only paginates complete rows. */
export function RecordTable({children, label = "Records", paginate = true, ...props}: TableHTMLAttributes<HTMLTableElement> & {label?:string; paginate?:boolean}) {
  const [page,setPage] = useState(0), [size,setSize] = useState(25);
  const parts = Children.toArray(children);
  const bodies = parts.filter((node): node is ReactElement<{children?:ReactNode}> => isValidElement(node) && node.type === "tbody");
  const rows = bodies.length === 1 ? flatten(bodies[0].props.children) : [];
  // Grouped/multi-body tables and rowspan layouts must remain intact.
  const safe = rows.every(row => isValidElement<{children?:ReactNode}>(row) && row.type === "tr" && flatten(row.props.children).every(cell => !isValidElement<{rowSpan?:number}>(cell) || !cell.props.rowSpan || cell.props.rowSpan === 1));
  const paged = paginate && safe && bodies.length === 1;
  const p = collectionPage(rows.length,page,size);
  const body = bodies[0];
  return <div className="nxt-record-table"><div className="nxt-table-scroll" tabIndex={0} role="region" aria-label={`${label} table`}><table {...props}>{paged ? parts.map(node => node === body ? cloneElement(body,{children:rows.slice(p.start,p.end)}) : node) : children}</table></div>{paged && <CollectionPagination total={rows.length} page={p.current} pageSize={size} onPageChange={setPage} onPageSizeChange={setSize} label={label} scope="loaded"/>}</div>;
}
