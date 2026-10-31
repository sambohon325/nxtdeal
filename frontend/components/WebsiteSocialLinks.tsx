import { createElement } from "react";
import icons from "@/lib/websiteSocialIcons.json";

export function WebsiteSocialLinks({ links, label = "Connect with us" }: { links?: Record<string, string>; label?: string }) {
  const enabled = Object.entries(links || {}).filter(([key, url]) => key in icons && /^https:\/\//i.test(url));
  if (!enabled.length) return null;
  return <nav aria-label={label} className="site-socials">
    <p className="mb-3 text-sm font-semibold">{label}</p>
    <div className="flex flex-wrap gap-3">{enabled.map(([platform, url]) => <a href={url} key={platform} target="_blank" rel="noopener noreferrer" aria-label={platform} title={platform} style={{ background: "var(--site-accent, #192532)", color: "var(--site-buttonInk, #fff)", borderRadius: "calc(var(--site-radius, 12px) * .6)", width: 42, height: 42, display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        {icons[platform as keyof typeof icons].map((node, index) => createElement(node.tag, { ...node.attrs, key: index }))}
      </svg>
    </a>)}</div>
  </nav>;
}
