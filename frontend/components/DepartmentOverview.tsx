"use client";

import {Children, cloneElement, isValidElement, type ButtonHTMLAttributes, type ReactNode} from "react";
import { WorkspaceIcon } from "./WorkspaceIcon";
import styles from "./DepartmentOverview.module.css";

export function OverviewHeader({department, title, description, children, context="At a glance"}: {department:string; title:string; description:string; children?:ReactNode; context?:string}) {
  const actions = Children.map(children, child => isValidElement<ButtonHTMLAttributes<HTMLButtonElement>>(child) && child.type === "button" ? cloneElement(child,{className:"work-button"}) : child);
  return <header data-work-page-header className={styles.heading}><div><p className={styles.eyebrow}>{department} · {context}</p><h2>{title}</h2><p>{description}</p></div>{children && <div className={styles.headerActions}>{actions}</div>}</header>;
}

export type OverviewMetric = {label:string; value:number | string | null | undefined; icon:string; detail:string; action?:string; onClick?:()=>void; attention?:boolean; selected?:boolean; disabled?:boolean};
export function OverviewMetrics({items, label="Department snapshot"}: {items:OverviewMetric[]; label?:string}) {
  return <section className={styles.metrics} data-count={items.length} aria-label={label}>{items.map(item=><article key={item.label} className={`${styles.metric} ${item.attention ? styles.attention : ""} ${item.selected ? styles.selected : ""}`}><div className={styles.metricTop}><span className={styles.metricIcon}><WorkspaceIcon name={item.icon}/></span><h3>{item.label}</h3></div><strong className={styles.value}>{item.value ?? "—"}</strong><p>{item.detail}</p>{item.onClick && <button type="button" disabled={item.disabled} onClick={item.onClick} aria-pressed={item.selected} aria-label={`${item.action ?? "View work"}: ${item.label}`}>{item.action ?? "View work"}<span aria-hidden="true">→</span></button>}</article>)}</section>;
}

export function OverviewActions({items}: {items:{label:string; icon?:string; onClick:()=>void}[]}) {
  if (!items.length) return null;
  return <section className={styles.quick}><h3>Quick actions</h3><nav aria-label="Department quick actions">{items.map(item=><button key={item.label} onClick={item.onClick}><WorkspaceIcon name={item.icon ?? "route"}/><span>{item.label}</span><span aria-hidden="true">→</span></button>)}</nav></section>;
}
