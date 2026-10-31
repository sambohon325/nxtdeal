// Auto-translation dictionary for the dealeros.xyz marketing site (2026-07-25).
//
// Sam asked for an EN / FR / ES toggle that works "automatically, like Google Translate" but as our
// OWN branded switch, with the correct dialects (Canadian French, Mexican Spanish). Rather than a
// paid third-party overlay or rewriting every page into t() calls, the approach is:
//   1. English copy stays in the pages exactly as written (single source of truth).
//   2. This file holds a lookup keyed by the exact English string → its fr-CA / es-MX translation.
//   3. components/i18n/LanguageProvider walks the rendered DOM text nodes and swaps them live.
//
// The raw tuples live in ./generated (machine-translated once, tuned for fr-CA / es-MX, and
// re-generated whenever English copy changes). Keeping the data in a separate file keeps this
// module tiny and lets the generator overwrite just the data.

import { RAW } from "./generated";

export type Locale = "en" | "fr" | "es";
export const LOCALES: Locale[] = ["en", "fr", "es"];
export const LOCALE_LABELS: Record<Locale, string> = { en: "EN", fr: "FR", es: "ES" };

export type Entry = { fr: string; es: string };

// Build the { [englishTrimmed]: {fr, es} } lookup once at module load.
export const translations: Record<string, Entry> = (() => {
  const map: Record<string, Entry> = {};
  for (const [en, fr, es] of RAW) {
    const key = en.trim();
    if (key) map[key] = { fr, es };
  }
  return map;
})();

export function translate(englishTrimmed: string, locale: Locale): string | undefined {
  if (locale === "en") return englishTrimmed;
  const entry = translations[englishTrimmed];
  return entry ? entry[locale] : undefined;
}
