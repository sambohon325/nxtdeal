"use client";

import { useId } from "react";

// Optical-size vector artwork: shared ice-glass materials, distinct app silhouettes.
const glyphs = {
  growth: "M7 24V18M14 24V13M21 24V8 M6 12L13 7L18 10L25 4 M20 4H25V9",
  sales: "M5 10H27V26H5Z M11 10V6H21V10 M5 16L16 20L27 16 M14 18V22H18V18",
  reception: "M6 23H26 M8 21C8 10 24 10 24 21Z M14 10H18 M16 10V7 M4 26H28",
  showroom: "M3 26V7H29V26 M3 12H29 M7 7V12 M13 7V12 M19 7V12 M25 7V12 M8 26V20L10 17H22L24 20V26 M8 22H24 M11 25H13 M19 25H21",
  garage: "M4 27V11L16 4L28 11V27 M8 11H24 M9 26V21L11 17H21L23 21V26 M9 22H23 M12 25H13 M19 25H20",
  kiosk: "M7 4H25V22H7Z M10 7H22V18H10Z M13 22V27H19V22 M10 28H22 M14 12L16 14L20 10",
  service: "M20 5A7 7 0 0 0 12 14L5 21A4 4 0 0 0 11 27L18 20A7 7 0 0 0 27 12L22 15L17 10Z M8 24L9 23",
  calendar: "M6 7H26V27H6Z M6 13H26 M11 4V10 M21 4V10 M11 18H14 M19 18H22 M11 23H14",
  people: "M12 16A5 5 0 1 0 12 6A5 5 0 0 0 12 16 M3 27V24C3 16 21 16 21 24V27 M22 7C28 7 28 16 22 16 M24 20C28 20 29 24 29 27",
  car: "M4 25V18L8 9H24L28 18V25 M4 18H28 M8 23H11 M21 23H24 M7 25V28 M25 25V28",
  star: "M16 4L20 12L29 13L22 20L24 29L16 24L8 29L10 20L3 13L12 12Z",
  coach: "M16 5L19 13L27 16L19 19L16 27L13 19L5 16L13 13Z M25 4V10 M22 7H28",
  settings: "M12 5H20L21 9L25 11L28 11L30 18L26 20L24 24L24 27L17 29L14 25L10 24L7 25L3 19L6 15L7 11L6 8Z M21 17A5 5 0 1 0 11 17A5 5 0 0 0 21 17",
  gift: "M5 14H27V20H5Z M7 20V28H25V20 M16 14V28 M16 14C5 14 6 3 12 6C16 8 16 14 16 14C27 14 26 3 20 6C16 8 16 14 16 14",
  wallet: "M5 8H25V27H5Z M5 8L23 4V8 M19 15H28V22H19Z M23 18V19",
  chart: "M5 5V27H28 M10 23V17 M17 23V12 M24 23V7",
  queue: "M6 8H26 M6 16H21 M6 24H16 M24 20L28 24L24 28",
  calculator: "M7 4H25V28H7Z M11 8H21V13H11Z M11 18H13 M19 18H21 M11 23H13 M19 23H21",
  chat: "M5 5H27V22H14L7 28V22H5Z M10 11H22 M10 16H19",
  check: "M6 16L13 23L27 8",
  phone: "M8 4L13 10L10 14C12 19 15 22 19 23L23 20L28 25C24 32 17 28 11 22C5 16 1 8 8 4Z",
  contact: "M7 5H27V28H7Z M4 10H9 M4 17H9 M4 24H9 M21 13A4 4 0 1 0 13 13A4 4 0 0 0 21 13 M12 23C12 17 22 17 22 23",
  sign: "M5 6H27V22H5Z M16 22V29 M11 29H21 M10 14H22 M18 10L22 14L18 18",
  search: "M23 14A9 9 0 1 0 5 14A9 9 0 0 0 23 14 M21 21L28 28",
  heart: "M16 27L5 16C-1 6 10 1 16 10C22 1 33 6 27 16Z",
  deal: "M3 12L8 7L14 10L18 7L29 13L24 23L19 28L11 24L3 16 M14 10L10 15L14 18L19 14L24 19 M11 24L14 21 M16 26L19 23",
  edit: "M6 24L8 17L22 3L29 10L15 24Z M18 7L25 14 M6 24L13 22 M5 29H27",
  location: "M16 29S5 19 5 12A11 11 0 0 1 27 12C27 19 16 29 16 29Z M20 12A4 4 0 1 0 12 12A4 4 0 0 0 20 12",
  bell: "M6 23L9 19V12A7 7 0 0 1 23 12V19L26 23Z M13 27H19 M16 3V5",
  time: "M27 16A11 11 0 1 0 5 16A11 11 0 0 0 27 16 M16 8V16L22 20",
  coffee: "M5 12H23V21C23 30 5 30 5 21Z M23 14H27C32 14 30 22 23 22 M4 29H25 M10 4V8 M17 3V7",
  clipboard: "M11 6H6V28H26V6H21 M11 3H21V10H11Z M11 16H21 M11 22H19",
  camera: "M4 10H10L12 6H20L22 10H28V27H4Z M22 18A6 6 0 1 0 10 18A6 6 0 0 0 22 18",
  parts: "M16 3L27 9V23L16 29L5 23V9Z M22 16A6 6 0 1 0 10 16A6 6 0 0 0 22 16",
} as const;

export type AppIconName = keyof typeof glyphs;
const legacyGlyphs: Record<string, AppIconName> = {"🚀": "growth", "📅": "calendar", "👥": "people", "🚗": "garage", "🌟": "star", "💬": "chat", "⚙️": "settings", "🎁": "gift", "💰": "wallet", "💼": "sales", "📊": "chart", "🙋": "queue", "🧮": "calculator", "🛎️": "reception", "✅": "check", "🗓️": "calendar", "☎️": "phone", "📇": "contact", "🪧": "sign", "🏬": "showroom", "🔎": "search", "❤️": "heart", "🤝": "deal", "🚙": "car", "📆": "calendar", "✍️": "edit", "📍": "location", "🔔": "bell", "🖥️": "kiosk", "⏳": "time", "☕": "coffee", "🛠️": "service", "📋": "clipboard", "📷": "camera", "🔩": "parts", "📈": "growth"};

/** Decorative beside the existing app/tab label; no duplicate screen-reader name. */
export function AppIcon({ name, className = "h-12 w-12", tile = true }: {
  name: AppIconName | string; className?: string; tile?: boolean;
}) {
  const glyph = glyphs[(legacyGlyphs[name] ?? name) as AppIconName] ?? glyphs.growth;
  const id = useId().replace(/:/g, "");
  if (!tile) return <svg aria-hidden="true" focusable="false" viewBox="0 0 32 32" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d={glyph} /></svg>;
  return (
    <svg aria-hidden="true" focusable="false" viewBox="0 0 64 64" className={`shrink-0 ${className}`} fill="none">
      <defs>
        <linearGradient id={`${id}-rim`} x1="8" y1="5" x2="56" y2="61" gradientUnits="userSpaceOnUse"><stop stopColor="#e9f8ff"/><stop offset=".23" stopColor="#5eb5e3"/><stop offset=".52" stopColor="#233849"/><stop offset=".78" stopColor="#8ed9ff"/><stop offset="1" stopColor="#daeaf3"/></linearGradient>
        <linearGradient id={`${id}-glass`} x1="10" y1="7" x2="48" y2="60" gradientUnits="userSpaceOnUse"><stop stopColor="#264657"/><stop offset=".27" stopColor="#08131c"/><stop offset=".62" stopColor="#02080d"/><stop offset="1" stopColor="#12354a"/></linearGradient>
        <linearGradient id={`${id}-light`} x1="16" y1="14" x2="46" y2="51" gradientUnits="userSpaceOnUse"><stop stopColor="#fff"/><stop offset=".42" stopColor="#d5e9f5"/><stop offset="1" stopColor="#6cc7fa"/></linearGradient>
      </defs>
      <rect x="3" y="3" width="58" height="58" rx="8" fill={`url(#${id}-glass)`} stroke={`url(#${id}-rim)`} strokeWidth="1"/>
      <path d={glyph} transform="translate(13 12) scale(1.18)" fill="#a9d5ec" fillOpacity=".07" stroke={`url(#${id}-light)`} strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}
