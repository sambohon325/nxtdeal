// Deployment boundaries only. API authentication remains independently enforced.
const within = (path: string, root: string) => path === root || path.startsWith(`${root}/`);
const assets = (path: string) => ["/_next", "/brand", "/fonts"].some(root => within(path, root)) ||
  ["/favicon.ico", "/icon.png", "/apple-icon.png", "/manifest.webmanifest", "/robots.txt"].includes(path);

export function deploymentRedirect(mode: string | undefined, path: string): string | null {
  if (!["marketing", "hub", "apps"].includes(mode ?? "")) return null;
  if (assets(path)) return null;
  if (mode === "marketing") return path === "/" ? null : "/";
  if (within(path, "/api")) return null;
  if (mode === "hub") return within(path, "/hub-console") ? null : "/hub-console";
  if (mode === "apps") return ["/apps", "/approve", "/checkin", "/pay", "/rep"].some(root => within(path, root)) ? null : "/apps";
  return null;
}
