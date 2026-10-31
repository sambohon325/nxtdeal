"use client";

import type {ComponentPropsWithRef, HTMLAttributes, InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes, ReactNode} from "react";
import {useEffect, useState} from "react";
import {createPortal} from "react-dom";
import "./WorkspaceUi.css";

/** Action controls have one size and treatment; navigation cards are separate. */
export function WorkButton({variant="secondary", className="", type="button", ...props}: ComponentPropsWithRef<"button"> & {variant?:"primary"|"secondary"|"danger"|"quiet"}) {
  return <button {...props} type={type} className={`work-button ${className}`} data-work-variant={variant}/>;
}

export function WorkInput({className="", ...props}:InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`work-control ${className}`}/>;
}
export function WorkSelect({className="", ...props}:SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`work-control ${className}`}/>;
}
export function WorkTextarea({className="", ...props}:TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`work-control ${className}`}/>;
}

/** Compact snapshot for a working list; overview cards include navigation. */
export function WorkStat({label,value,tone}:{label:string;value:ReactNode;tone?:string}) {
  return <div className="work-stat"><span>{label}</span><strong className={tone}>{value ?? "—"}</strong></div>;
}

/** Glass panels create fixed-position containing blocks. Mount overlays at the
 * theme root so scrolling a list cannot clip its form or hide its close action. */
export function WorkOverlay({className="",children,...props}:HTMLAttributes<HTMLDivElement>) {
  const modal=className.split(/\s+/).includes("fixed");
  const [host,setHost]=useState<Element|null>(null);
  useEffect(()=>{if(modal)setHost(document.querySelector("[data-nxt-glass]") ?? document.body);},[modal]);
  if(!modal)return <div {...props} className={className}>{children}</div>;
  if(!host)return null;
  return createPortal(<div {...props} data-department-work="" className={`nxt-workspace-content work-overlay ${className}`}>{children}</div>,host);
}

export function WorkToolbar({children, label="List filters", ...props}: HTMLAttributes<HTMLDivElement> & {label?:string}) {
  return <div {...props} className={`work-toolbar ${props.className??""}`} role="group" aria-label={label}>{children}</div>;
}

export function WorkSection({title, description, actions, children}: {title:string;description?:string;actions?:ReactNode;children:ReactNode}) {
  return <section className="work-section"><header className="work-section-heading"><div><h3>{title}</h3>{description&&<p>{description}</p>}</div>{actions&&<div className="work-actions">{actions}</div>}</header>{children}</section>;
}

export function WorkEmpty({title,description,children}: {title:string;description?:string;children?:ReactNode}) {
  return <div className="work-empty"><h4>{title}</h4>{description&&<p>{description}</p>}{children&&<div className="work-actions">{children}</div>}</div>;
}
