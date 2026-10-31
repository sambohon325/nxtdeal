"use client";
import {Children, useState, type ReactNode} from "react";
import {CollectionPagination, collectionPage} from "./CollectionPagination";

/** The same paging contract for cards, activity histories, and plain lists. */
export function RecordCollection({children,label="Records",busy=false,list=false}: {children:ReactNode;label?:string;busy?:boolean;list?:boolean}) {
  const [page,setPage]=useState(0),[size,setSize]=useState(25);
  const rows=Children.toArray(children),p=collectionPage(rows.length,page,size);
  const Footer=list?"li":"div";
  return <>{rows.slice(p.start,p.end)}<Footer className="nxt-collection-footer"><CollectionPagination total={rows.length} page={p.current} pageSize={size} onPageChange={setPage} onPageSizeChange={setSize} label={label} busy={busy} scope="loaded"/></Footer></>;
}
