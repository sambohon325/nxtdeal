"use client";

import { useEffect, useState } from "react";

const WORDS = ["Sales", "Marketing", "DMS", "F&I", "Deal"];

export function NextDealHeadline() {
  const [text, setText] = useState("Deal");
  const [fading, setFading] = useState(false);

  useEffect(() => {
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let timer: ReturnType<typeof setTimeout>;
    let stopped = false;
    function start() {
      clearTimeout(timer);
      stopped = motion.matches;
      setFading(false);
      setText(stopped ? "Deal" : "");
      if (stopped) return;
      let word = 0;
      let letter = 0;
      function type() {
        if (stopped) return;
        letter += 1;
        setText(WORDS[word].slice(0, letter));
        if (letter < WORDS[word].length) {
          timer = setTimeout(type, 105);
        } else if (word < WORDS.length - 1) {
          timer = setTimeout(() => {
            setFading(true);
            timer = setTimeout(() => {
              word += 1;
              letter = 0;
              setText("");
              setFading(false);
              timer = setTimeout(type, 140);
            }, 400);
          }, 1100);
        }
      }
      timer = setTimeout(type, 300);
    }
    start();
    motion.addEventListener("change", start);
    return () => {
      stopped = true;
      clearTimeout(timer);
      motion.removeEventListener("change", start);
    };
  }, []);

  return (
    <h1 className="nxt-hero-title mb-6 font-brand text-5xl sm:text-6xl font-bold leading-[1.05] tracking-tight">
      <span className="sr-only">Your Next Deal</span>
      <span aria-hidden="true" className="block">
        <span className="nxt-metal-text">Your Next</span>
        <span className={`nxt-hero-word block min-h-[1.05em] transition-opacity duration-[400ms] motion-reduce:transition-none ${fading ? "opacity-0" : "opacity-100"}`}>
          {text || "\u00a0"}
        </span>
      </span>
    </h1>
  );
}
