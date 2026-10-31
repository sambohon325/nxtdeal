"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

const documentMarkup = '<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>html,body{margin:0;padding:0;background:#fff}*{scrollbar-width:none!important}::-webkit-scrollbar{display:none!important}</style></head><body><div id="website-preview-root"></div></body></html>';

/** Real responsive viewport with React content, no frame scripts or credentials.
 * Same-origin access lets the parent mount React; scripts/forms remain sandboxed.
 */
export function WebsitePreviewFrame({ device, children }: { device: "desktop" | "mobile"; children: ReactNode }) {
  const container = useRef<HTMLDivElement>(null);
  const frame = useRef<HTMLIFrameElement>(null);
  const [availableWidth, setAvailableWidth] = useState(800);
  const [mount, setMount] = useState<HTMLElement | null>(null);
  const width = device === "mobile" ? 390 : 1280;
  const scale = Math.min(1, availableWidth / width);
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver(entries => setAvailableWidth(entries[0].contentRect.width));
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const element = frame.current;
    if (!element) return;
    function mountPreview() {
      const frameDocument = element?.contentDocument;
      const root = frameDocument?.getElementById("website-preview-root");
      if (!frameDocument || !root) return;
      if (!frameDocument.head.querySelector("[data-preview-style]")) {
        document.head.querySelectorAll('link[rel="stylesheet"],style').forEach(style => {
          const copy = style.cloneNode(true) as HTMLElement;
          copy.setAttribute("data-preview-style", "");
          frameDocument.head.appendChild(copy);
        });
      }
      setMount(root);
    }
    element.addEventListener("load", mountPreview);
    mountPreview();
    return () => element.removeEventListener("load", mountPreview);
  }, []);
  return <div ref={container} style={{ width: "100%", minWidth: 0, display: "flex", justifyContent: "center" }}>
    <iframe ref={frame} title={`${device === "mobile" ? "Mobile" : "Desktop"} live website preview`}
      sandbox="allow-same-origin" srcDoc={documentMarkup}
      style={{ width, height: 620 / scale, zoom: scale, border: 0, flexShrink: 0, background: "white" }} />
    {mount && createPortal(children, mount)}
  </div>;
}
