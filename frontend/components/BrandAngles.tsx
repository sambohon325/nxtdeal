"use client";

// Compatibility exports let existing boards adopt Chrono styling without losing
// their established controls or navigation. The old geometric treatment is retired.
import type { CSSProperties, ReactNode } from "react";

export const BRAND_COLORS = {
  blue: "#c6d8e2", teal: "#d6e0e5", yellow: "#d4e0ec", red: "#94a9bc",
} as const;
export const BRAND_RIBBON_ORDER: (keyof typeof BRAND_COLORS)[] = ["blue", "teal", "yellow", "red"];

export function angledClip(_bite: number = 12): CSSProperties {
  return { borderRadius: 10 };
}

export function BrandRibbon({ height: _height = 1, className = "" }: { height?: number; className?: string }) {
  return <div aria-hidden="true" className={`w-full shrink-0 ${className}`} style={{ height: 1, background: "linear-gradient(90deg, transparent, rgba(180,210,230,.12), transparent)" }} />;
}

export function AngledGlow({ color: _color, className = "", style }: {
  color: keyof typeof BRAND_COLORS; className?: string; style?: CSSProperties;
}) {
  return <div aria-hidden="true" className={`pointer-events-none ${className}`} style={{ background: "radial-gradient(ellipse, rgba(150,190,210,.025), transparent 65%)", filter: "blur(40px)", ...style }} />;
}

export function AngledCornerAccent({ color: _color, size = 28 }: { color: keyof typeof BRAND_COLORS; size?: number }) {
  return <div aria-hidden="true" className="absolute top-0 left-6 pointer-events-none" style={{ width: size, height: 1, background: "rgba(255,255,255,.3)" }} />;
}

export function AngledBadge({ color, children, className = "" }: {
  color: keyof typeof BRAND_COLORS; children: ReactNode; className?: string;
}) {
  return <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium tracking-wide ${className}`} style={{ background: "rgba(255,255,255,.07)", color: BRAND_COLORS[color], border: "1px solid rgba(255,255,255,.15)" }}>{children}</span>;
}
