// Shared small icon set (2026-07-13) -- replaces two emoji/cartoon stand-ins that
// didn't match the rest of the UI's hand-drawn line-icon style (every other icon in
// this app -- the Department Intelligence panel, HelpWidget, KnowledgeBaseWidget,
// ChatDock -- is a plain inline
// stroke SVG, currentColor, no icon library dependency). Sam: "much more themed,
// elegant... neural circuit / brain... something classier" for the bot, and a nicer
// pin glyph to replace the 📌 emoji used across all four pages + ChatDock.
//
// Kept as small, self-contained components (not a big icon-library import) to match
// the existing convention -- every icon in this codebase so far has been an inline
// <svg>, not lucide-react or a similar dependency.

export function NeuralIcon({ className, size = 22 }: { className?: string; size?: number }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      {/* Chip outline -- an AI/neural processor rather than a cartoon robot body */}
      <rect x="6" y="6" width="12" height="12" rx="3" />
      {/* Four short pin legs, like a circuit chip */}
      <path d="M12 6V3M12 21v-3M6 12H3M21 12h-3" />
      {/* A tiny hub-and-spoke neural network inside the chip */}
      <circle cx="9" cy="9" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="15" cy="9" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="9" cy="15" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="15" cy="15" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="1.1" fill="currentColor" stroke="none" />
      <path
        d="M9.6 9.6 11.2 11.2M14.4 9.6 12.8 11.2M9.6 14.4 11.2 12.8M14.4 14.4 12.8 12.8"
        strokeWidth="1.2"
        opacity="0.8"
      />
    </svg>
  );
}

export function RobotIcon({ className, size = 22 }: { className?: string; size?: number }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      {/* Reverted back to the session-41 bot icon (2026-07-15, session 72) -- Sam liked
          the black/turquoise BotWidget color scheme from the session-71 chat-bubble
          redesign, but wanted the icon itself back to this one: a simple, modern robot
          silhouette -- rounded head, antenna, small side "ears", two eyes and a flat
          mouth. Stroke-based (currentColor), so BotWidget.tsx's text-brand-teal still
          colors it turquoise against the black button with no changes needed there. */}
      <path d="M12 6.5V4" />
      <circle cx="12" cy="3" r="1" fill="currentColor" stroke="none" />
      <rect x="5" y="6.5" width="14" height="11" rx="4" />
      <path d="M3.5 10.5v3M20.5 10.5v3" />
      <rect x="8.5" y="10.5" width="2" height="3" rx="1" fill="currentColor" stroke="none" />
      <rect x="13.5" y="10.5" width="2" height="3" rx="1" fill="currentColor" stroke="none" />
      <path d="M9 15h6" />
    </svg>
  );
}

export function PinIcon({
  className,
  size = 14,
  filled = false,
}: {
  className?: string;
  size?: number;
  filled?: boolean;
}) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
      {!filled && <circle cx="12" cy="10" r="3" />}
    </svg>
  );
}
