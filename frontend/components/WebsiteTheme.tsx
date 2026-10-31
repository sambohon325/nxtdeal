import type { CSSProperties, ReactNode } from "react";
import tokens from "@/lib/websiteThemeTokens.json";
import styles from "./WebsiteTheme.module.css";

export function WebsiteTheme({ themeId, children }: { themeId?: string; children: ReactNode }) {
  const palette = tokens[themeId as keyof typeof tokens];
  if (!palette) return <>{children}</>;
  const variables = Object.fromEntries(Object.entries(palette).map(([key, value]) => [`--site-${key}`, value])) as CSSProperties;
  return <div className={styles.root} data-website-theme={themeId} style={variables}>{children}</div>;
}
