"use client";

// Live DOM auto-translation for the marketing site (2026-07-25). See lib/i18n/dictionary.ts for the
// why. This provider:
//   - holds the current locale (persisted to localStorage, defaults to English),
//   - on locale change, walks every text node under its root and swaps English → fr-CA / es-MX
//     using the dictionary, restoring the captured English when switched back to EN,
//   - keeps a MutationObserver running so route changes / late-rendered content translate too,
//     while ignoring its OWN writes so it never fights itself or corrupts the English source.
//
// English source is captured ONCE per text node (the first time it's seen, which is always while
// the node holds React's English output) and stored in a persistent map, so FR→ES→EN round-trips
// stay correct. Strings with no dictionary entry are left in English — graceful partial coverage.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { translations, LOCALE_LABELS, LOCALES, type Locale } from "@/lib/i18n/dictionary";

const STORAGE_KEY = "dealeros_locale";

type Ctx = { locale: Locale; setLocale: (l: Locale) => void };
const LocaleContext = createContext<Ctx>({ locale: "en", setLocale: () => {} });
export const useLocale = () => useContext(LocaleContext);

const hasLetter = (s: string) => /[A-Za-zÀ-ÿ]/.test(s);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("en");
  const rootRef = useRef<HTMLDivElement | null>(null);
  const localeRef = useRef<Locale>("en");

  // Persistent across locale changes so the true English source is never lost.
  const originals = useRef<WeakMap<Text, string>>(new WeakMap());
  const applied = useRef<WeakMap<Text, string>>(new WeakMap());

  // Hydrate a saved choice.
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY) as Locale | null;
      if (saved && LOCALES.includes(saved) && saved !== "en") setLocaleState(saved);
    } catch {
      /* ignore */
    }
  }, []);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    try {
      localStorage.setItem(STORAGE_KEY, l);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    localeRef.current = locale;
    const root = rootRef.current;
    if (!root) return;

    const skip = (node: Text): boolean => {
      const p = node.parentElement;
      if (!p) return true;
      const tag = p.tagName;
      if (tag === "SCRIPT" || tag === "STYLE" || tag === "NOSCRIPT" || tag === "CODE" || tag === "PRE")
        return true;
      if (p.closest("[data-no-translate]")) return true;
      return false;
    };

    const applyNode = (node: Text) => {
      if (skip(node)) return;
      const current = node.nodeValue ?? "";
      if (!hasLetter(current)) return;

      // Capture the English source the first time we see this node (it holds English now).
      if (!originals.current.has(node)) originals.current.set(node, current);
      const original = originals.current.get(node)!;
      const key = original.trim();
      const loc = localeRef.current;

      let next: string;
      if (loc === "en") {
        next = original;
      } else {
        const entry = translations[key];
        if (entry && entry[loc]) {
          const lead = original.match(/^\s*/)?.[0] ?? "";
          const tail = original.match(/\s*$/)?.[0] ?? "";
          next = lead + entry[loc] + tail;
        } else {
          next = original; // no translation available — keep English
        }
      }
      if (node.nodeValue !== next) {
        node.nodeValue = next;
        applied.current.set(node, next);
      } else {
        applied.current.set(node, next);
      }
    };

    const walk = (el: Node) => {
      const tw = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      const nodes: Text[] = [];
      let cur = tw.nextNode();
      while (cur) {
        nodes.push(cur as Text);
        cur = tw.nextNode();
      }
      nodes.forEach(applyNode);
    };

    walk(root);

    const observer = new MutationObserver((mutations) => {
      for (const m of mutations) {
        if (m.type === "childList") {
          m.addedNodes.forEach((n) => {
            if (n.nodeType === Node.TEXT_NODE) applyNode(n as Text);
            else if (n.nodeType === Node.ELEMENT_NODE) walk(n as Element);
          });
        } else if (m.type === "characterData" && m.target.nodeType === Node.TEXT_NODE) {
          const t = m.target as Text;
          // Ignore our own writes; a genuine React text update means new English source.
          if (applied.current.get(t) === t.nodeValue) continue;
          originals.current.delete(t);
          applied.current.delete(t);
          applyNode(t);
        }
      }
    });
    observer.observe(root, { childList: true, subtree: true, characterData: true });

    return () => observer.disconnect();
  }, [locale]);

  return (
    <LocaleContext.Provider value={{ locale, setLocale }}>
      {/* display:contents — the ref/observer still work, but this wrapper adds no layout box, so it
          never breaks the parent→child height chain the scroll container relies on. */}
      <div ref={rootRef} data-i18n-root className="contents">
        {children}
      </div>
    </LocaleContext.Provider>
  );
}

// The EN | FR | ES switch shown in the marketing nav. Marked data-no-translate so the engine never
// touches its own labels.
export function LanguageToggle({ className = "" }: { className?: string }) {
  const { locale, setLocale } = useLocale();
  return (
    <div
      data-no-translate
      className={`inline-flex items-center overflow-hidden border border-zinc-700 ${className}`}
      style={{ clipPath: "polygon(6px 0, 100% 0, calc(100% - 6px) 100%, 0 100%)" }}
      role="group"
      aria-label="Language"
    >
      {LOCALES.map((code) => {
        const active = locale === code;
        return (
          <button
            key={code}
            type="button"
            onClick={() => setLocale(code)}
            aria-pressed={active}
            className={
              active
                ? "px-2.5 py-1.5 text-[10px] font-brand font-bold tracking-wide bg-brand-teal text-black"
                : "px-2.5 py-1.5 text-[10px] font-brand font-semibold tracking-wide text-zinc-400 hover:text-white transition"
            }
          >
            {LOCALE_LABELS[code]}
          </button>
        );
      })}
    </div>
  );
}
