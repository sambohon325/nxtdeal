"use client";

import { mediaImageUrl } from "@/lib/mediaLibrary";
import { createElement, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import catalogue from "@/lib/websiteStudioCatalogue.json";

type HeroNode = string | { tag: string; attrs: Record<string, string>; binding?: string; children: HeroNode[] };
type HeroDesign = { id: string; css: string; bodyClass: string; hero: HeroNode };
const attributeNames: Record<string, string> = { class: "className", viewbox: "viewBox", "stroke-width": "strokeWidth", "stroke-linecap": "strokeLinecap", "stroke-linejoin": "strokeLinejoin" };
const pageForAnchor: Record<string, string> = { inventory: "inventory", "payment-shop": "financing", financing: "financing", team: "about", contact: "contact", service: "contact" };
const cache = new Map<string, Promise<HeroDesign>>();

function loadDesign(id: string) {
  if (!cache.has(id)) cache.set(id, fetch(`/website-studio/themes/${id}.json`).then(response => {
    if (!response.ok) throw new Error("Design artwork could not be loaded.");
    return response.json() as Promise<HeroDesign>;
  }).catch(error => { cache.delete(id); throw error; }));
  return cache.get(id)!;
}

/** Trusted build-time structure, React-escaped dealer fields, and isolated styles.
 * No HTML injection, demo JavaScript, copied inventory or inline event handlers.
 */
export function ApprovedWebsiteHero({ themeId, fields, websiteId, websiteName, editable, onFieldEdit }: {
  themeId: string; fields: Record<string, unknown>; websiteId?: string; websiteName?: string;
  editable?: boolean; onFieldEdit?: (key: string, value: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [shadow, setShadow] = useState<ShadowRoot | null>(null);
  const [design, setDesign] = useState<HeroDesign | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (host.current) setShadow(host.current.shadowRoot || host.current.attachShadow({ mode: "open" }));
  }, []);
  useEffect(() => {
    let active = true;
    setDesign(null);
    setError("");
    if (!catalogue.themes.some(theme => theme.id === themeId)) return;
    loadDesign(themeId).then(value => { if (active) setDesign(value); }).catch(error => { if (active) setError(error.message); });
    return () => { active = false; };
  }, [themeId]);
  function render(node: HeroNode, key: string): ReactNode {
    if (typeof node === "string") {
      if (!websiteName) return node;
      return node.replace(/\b(?:LONE STAR(?: AUTO)?|UNION MOTOR|CONEXI[ÓO]N(?: AUTO)?|HIGH MESA|EVERGREEN(?: AUTO)?|METROLINE AUTO|STERLING MOTOR CO\.?|DAYBREAK AUTO|AFTERHOURS AUTO|APEX AUTO|HARBOR AUTO|FOUNDRY AUTO|VECTOR AUTO|RALLY AUTO|WAYPOINT MOTOR CO\.?|SWITCH AUTO|REDLINE AUTO|PACIFIC AUTO|TEMPO AUTO|FIELDWORK AUTO)\b/gi, () => websiteName);
    }
    const props: Record<string, unknown> = { key };
    for (const [name, value] of Object.entries(node.attrs)) props[attributeNames[name] || name] = value;
    if (node.tag === "a") {
      const destination = pageForAnchor[(node.attrs.href || "").replace("#", "")] || "contact";
      props.href = websiteId ? `/site/${encodeURIComponent(websiteId)}?page=${destination}` : `#${destination}`;
      if (editable) props.onClick = (event: { preventDefault: () => void }) => event.preventDefault();
    }
    let children = node.children.map((child, index) => render(child, `${key}-${index}`));
    if (node.binding === "dealer_name" && websiteName) children = [websiteName];
    if (node.binding && fields[node.binding] != null && String(fields[node.binding]).trim()) {
      if (node.binding === "image_url") {
        const url = String(fields.image_url);
        if (/^https:\/\//.test(url) || /^\/(?!\/)/.test(url)) props.src = mediaImageUrl(url);
      } else children = [String(fields[node.binding])];
    }
    if (editable && node.binding && !["image_url", "dealer_name"].includes(node.binding)) {
      props.contentEditable = true;
      props.suppressContentEditableWarning = true;
      props.onBlur = (event: { currentTarget: HTMLElement }) => onFieldEdit?.(node.binding!, event.currentTarget.innerText);
      props.style = { outlineOffset: "5px" };
    }
    return createElement(node.tag, props, ...(node.tag === "img" || node.tag === "br" ? [] : children));
  }
  return <div ref={host}>
    {!design && <div role="status" style={{ padding: 40 }}>{error || "Loading design…"}</div>}
    {shadow && design && createPortal(<><style>{design.css}</style><div className={design.bodyClass}><main className="container">{render(design.hero, "hero")}</main></div></>, shadow)}
  </div>;
}
