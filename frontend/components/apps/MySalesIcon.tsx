import type { ReactNode } from "react";

// MySales-only icons matching the dealership navigation stroke style.
export const navigationGlyphs: Record<string, ReactNode> = {
  car: (
    <>
      <path d="m5 8 2-5h10l2 5M4 8h16v10H4zM6 18v3m12-3v3M4 13h16" />
      <path d="M6 10h2m8 0h2" />
    </>
  ),
  file: <path d="M6 2h8l5 5v15H6zM14 2v6h5M9 12h7m-7 4h7" />,
  shield: (
    <>
      <path d="m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6z" />
      <path d="m7 11 3 3 7-7" />
    </>
  ),
  search: (
    <>
      <circle cx="10" cy="10" r="7" />
      <path d="m15 15 7 7" />
    </>
  ),
  dollar: (
    <>
      <circle cx="12" cy="12" r="10" />
      <path d="M16 7h-5a3 3 0 0 0 0 6h2a3 3 0 0 1 0 6H8m4-15v17" />
    </>
  ),
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M7 2v6m10-6v6M3 11h18" />
    </>
  ),
  chart: <path d="M4 21V12m8 9V7m8 14V2" />,
  list: <path d="M8 5h14M8 12h14M8 19h14M2 5h1M2 12h1M2 19h1" />,
  people: (
    <>
      <circle cx="9" cy="7" r="3" />
      <path d="M3 21v-4a6 6 0 0 1 12 0v4M17 4a3 3 0 0 1 0 6m1 4c3 0 4 2 4 5v2" />
    </>
  ),
  sales: (
    <>
      <rect x="3" y="7" width="18" height="14" rx="2" />
      <path d="M8 7V3h8v4M3 12l9 3 9-3M12 13v4" />
    </>
  ),
  coach: (
    <>
      <rect x="6" y="6" width="12" height="12" rx="2" />
      <path d="M9 1v5m6-5v5M9 18v5m6-5v5M1 9h5m-5 6h5m12-6h5m-5 6h5M9 12l2 2 4-4" />
    </>
  ),
  settings: (
    <>
      <path d="M3 6h18M3 12h18M3 18h18" />
      <path d="M7 3v6m10 0v6m-7 0v6" />
    </>
  ),
  link: (
    <>
      <path d="m9 15 6-6m-7 4-2 2a3 3 0 0 0 4 4l3-3m-2-8 3-3a3 3 0 0 1 4 4l-2 2" />
    </>
  ),
  check: <path d="m4 12 5 5L20 6" />,
};
export function MySalesIcon({
  name,
  className = "h-6 w-6",
  children,
}: {
  name: string;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      {navigationGlyphs[name] ?? children ?? navigationGlyphs.list}
    </svg>
  );
}
