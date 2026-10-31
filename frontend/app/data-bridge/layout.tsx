"use client";
import type {ReactNode} from "react";
import {useRequireAuth} from "@/lib/auth";
export default function DataBridgeAccess({children}:{children:ReactNode}){
 const session=useRequireAuth("ADMIN");
 if(!session)return <p role="status">Checking administrator access…</p>;
 if(!session.isSystemAdmin)return <main><h1>NXTDeal system administration</h1><p>This tool requires separately provisioned NXTDeal system-admin access.</p><a href="/admin">Return to dealership administration</a></main>;
 return children;
}
