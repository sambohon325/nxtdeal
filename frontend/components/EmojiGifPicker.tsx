"use client";

// Emoji + GIF pickers for ChatDock's direct-message/channel compose bar (Sam: "on the
// direct messages, can we add in emoji selector and gif selector?"). Two small, focused
// popovers matching the existing "Attach a pin" popover's look and trigger pattern
// (components/ChatDock.tsx) rather than pulling in a heavy picker dependency.
//
// EmojiPicker is fully self-contained -- a curated, real Unicode emoji set grouped into
// a handful of common categories, no external API/dependency needed.
//
// GifPicker calls GIPHY's public search API directly from the browser (GIPHY's API is
// designed for client-side/CORS use with just an API key in the query string, no server
// round-trip needed). NEXT_PUBLIC_GIPHY_API_KEY defaults to GIPHY's own published public
// "beta" demo key (dc6zaTOxFJmzC -- documented at developers.giphy.com, rate-limited to
// ~42 requests/hour) so GIF search works out of the box in this dev/demo environment;
// set a real NEXT_PUBLIC_GIPHY_API_KEY (a free GIPHY API key, no cost) in production to
// lift that rate limit. Honest limitation, not hidden: the demo key WILL start
// rate-limiting under heavy use.

import { useEffect, useRef, useState } from "react";

const GIPHY_API_KEY = process.env.NEXT_PUBLIC_GIPHY_API_KEY ?? "dc6zaTOxFJmzC";

const EMOJI_GROUPS: { label: string; emoji: string[] }[] = [
  {
    label: "Smileys",
    emoji: [
      "😀", "😁", "😂", "🤣", "😊", "😉", "😍", "😘", "😎", "🤩",
      "🥳", "😇", "🙂", "🙃", "😅", "😢", "😭", "😡", "😱", "🤔",
      "😴", "🤗", "🤝", "🙌", "👏",
    ],
  },
  {
    label: "Gestures",
    emoji: [
      "👍", "👎", "👌", "🤞", "✌️", "🤙", "👋", "🙏", "💪", "🫡",
      "☝️", "👉", "👈", "👆", "👇",
    ],
  },
  {
    label: "Hearts",
    emoji: [
      "❤️", "🧡", "💛", "💚", "💙", "💜", "🖤", "🤍", "💔", "❤️‍🔥",
      "💯", "✨", "🔥", "⭐", "🎉",
    ],
  },
  {
    label: "Work",
    emoji: [
      "✅", "❌", "⚠️", "🚀", "📈", "📉", "💰", "💵", "🚗", "🔧",
      "📋", "📌", "⏰", "📅", "🗓️", "👀",
    ],
  },
];

export function EmojiPicker({ onSelect }: { onSelect: (emoji: string) => void }) {
  const [activeGroup, setActiveGroup] = useState(0);

  return (
    <div className="w-72">
      <div className="flex items-center gap-1 px-2 pt-2 pb-1 border-b border-zinc-800">
        {EMOJI_GROUPS.map((group, i) => (
          <button
            key={group.label}
            onClick={() => setActiveGroup(i)}
            className={
              i === activeGroup
                ? "text-[11px] px-2 py-0.5 rounded bg-zinc-800 text-white transition"
                : "text-[11px] px-2 py-0.5 rounded text-zinc-500 hover:text-white transition"
            }
          >
            {group.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-8 gap-0.5 p-2 max-h-40 overflow-y-auto">
        {EMOJI_GROUPS[activeGroup].emoji.map((emoji) => (
          <button
            key={emoji}
            onClick={() => onSelect(emoji)}
            className="text-lg leading-none w-7 h-7 flex items-center justify-center rounded hover:bg-zinc-800 transition"
          >
            {emoji}
          </button>
        ))}
      </div>
    </div>
  );
}

type GiphyImageData = { url: string; width: string; height: string };
type GiphyGif = {
  id: string;
  title: string;
  images: { fixed_width_small: GiphyImageData; original: GiphyImageData };
};

export function GifPicker({ onSelect }: { onSelect: (gifUrl: string) => void }) {
  const [query, setQuery] = useState("");
  const [gifs, setGifs] = useState<GiphyGif[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function runSearch(term: string) {
    setLoading(true);
    setError(null);

    const endpoint = term.trim()
      ? `https://api.giphy.com/v1/gifs/search?api_key=${GIPHY_API_KEY}&q=${encodeURIComponent(term)}&limit=15&rating=pg`
      : `https://api.giphy.com/v1/gifs/trending?api_key=${GIPHY_API_KEY}&limit=15&rating=pg`;

    fetch(endpoint)
      .then((r) => r.json())
      .then((d) => {
        if (d.data) {
          setGifs(d.data);
        } else {
          setError("Unable to load GIFs.");
        }
      })
      .catch(() => setError("Unable to reach GIPHY -- check your connection."))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    runSearch("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleQueryChange(value: string) {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => runSearch(value), 400);
  }

  return (
    <div className="w-80">
      <div className="p-2 border-b border-zinc-800">
        <input
          autoFocus
          value={query}
          onChange={(e) => handleQueryChange(e.target.value)}
          placeholder="Search GIPHY..."
          className="w-full h-8 px-2 text-xs rounded bg-zinc-950 border border-zinc-800 focus:outline-none focus:border-zinc-600"
        />
      </div>

      <div className="p-2 max-h-56 overflow-y-auto">
        {loading ? (
          <div className="text-xs text-zinc-600 p-2">Loading…</div>
        ) : error ? (
          <div className="text-xs text-red-400 p-2">{error}</div>
        ) : gifs.length === 0 ? (
          <div className="text-xs text-zinc-600 p-2">No GIFs found.</div>
        ) : (
          <div className="grid grid-cols-3 gap-1">
            {gifs.map((gif) => (
              <button
                key={gif.id}
                onClick={() => onSelect(gif.images.original.url)}
                title={gif.title}
                className="aspect-square rounded overflow-hidden border border-transparent hover:border-[#3FBCC4] transition bg-zinc-900"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={gif.images.fixed_width_small.url}
                  alt={gif.title}
                  className="w-full h-full object-cover"
                />
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="px-2 py-1 border-t border-zinc-900 text-[10px] text-zinc-600 text-right">
        Powered by GIPHY
      </div>
    </div>
  );
}

// A message whose entire (trimmed) content is a direct GIF/image URL -- from a GifPicker
// selection above -- renders as an inline image instead of plain linkified text. Kept as
// a plain heuristic on message.content rather than a new backend attachment type/field,
// same "don't add a store for something a string already represents" instinct as the
// rest of this codebase's messaging layer.
const IMAGE_URL_PATTERN = /^https:\/\/\S+\.(gif|webp|png|jpe?g)(\?\S*)?$/i;

export function isImageMessage(text: string): boolean {
  return IMAGE_URL_PATTERN.test(text.trim());
}

export function MessageImage({ url }: { url: string }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={url} alt="Shared GIF" className="max-w-full rounded-lg" style={{ maxHeight: 200 }} />
  );
}
