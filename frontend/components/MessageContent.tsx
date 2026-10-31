"use client";

import { useState, type ReactNode } from "react";
import { isImageMessage, MessageImage } from "@/components/EmojiGifPicker";
import { resolveVinToVehicleId } from "@/components/EntityHoverLink";

// Renders a chat message's text, turning anything that looks like a NXTDeal entity ID
// (core/id_generator.py's PREFIX-NNNNN scheme -- VEH/CUST/LEAD/FIN/LENDER/SRV/DOC/IMG/
// EMP/DEAL) into a clickable link that opens that entity's profile in the workspace
// panel. Same regex shape core/ai_api.py's _ENTITY_ID_PATTERN already uses for chat --
// duplicated client-side on purpose rather than having the backend annotate message
// text, since this is a pure display concern and /profile/{id} already enforces access
// (an inaccessible or unknown ID just won't resolve to anything useful when clicked, same
// as asking the AI assistant about it would). Session 28: "reference data from the graph
// when communicating... in the righthand side."
//
// A message that's entirely a GIF/image URL (sent via ChatDock's new GifPicker, session
// 75) renders as an inline image instead -- see EmojiGifPicker.tsx's isImageMessage.
//
// Session 76 sixth follow-up: a plain 17-char VIN mentioned in chat prose ("what's the
// status on 1G1ZD5ST0JF123456?") should be clickable too, same as a NXTDeal ID -- but a
// VIN isn't itself an entity ID (nothing to open at /profile/{vin}), so it needs its own
// second capture group and its own async-resolve-then-open click handler (VinChatLink
// below) rather than the plain synchronous onOpenEntity(match) every NXTDeal-ID match
// already uses. Kept as free-text extraction here (not an exact-full-string check like
// components/DepartmentWorkflowButtons.tsx's ValuePreview/components/MenuDashPanel.tsx's
// renderPrimitiveValue use for single structured values) since a chat message is prose,
// not one bare field value.
const ENTITY_ID_PATTERN = /\b([A-Z]{2,10}-\d{4,6})\b|\b([A-HJ-NPR-Z0-9]{17})\b/g;

function VinChatLink({ vin, onOpenEntity }: { vin: string; onOpenEntity: (entityId: string) => void }) {
  const [resolving, setResolving] = useState(false);

  function handleClick() {
    if (resolving) return;
    setResolving(true);
    resolveVinToVehicleId(vin)
      .then((vehicleId) => {
        if (vehicleId) onOpenEntity(vehicleId);
      })
      .finally(() => setResolving(false));
  }

  return (
    <button
      onClick={handleClick}
      disabled={resolving}
      title="Look up this VIN"
      className="text-[#3FBCC4] underline decoration-dotted hover:text-white transition disabled:opacity-50 disabled:cursor-wait"
    >
      {vin}
    </button>
  );
}

export function MessageContent({
  text,
  onOpenEntity,
}: {
  text: string;
  onOpenEntity: (entityId: string) => void;
}) {
  if (isImageMessage(text)) {
    return <MessageImage url={text.trim()} />;
  }

  const parts: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  ENTITY_ID_PATTERN.lastIndex = 0;

  while ((match = ENTITY_ID_PATTERN.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    const entityId = match[1];
    const vin = match[2];

    if (entityId) {
      parts.push(
        <button
          key={`${entityId}-${match.index}`}
          onClick={() => onOpenEntity(entityId)}
          className="text-[#3FBCC4] underline decoration-dotted hover:text-white transition"
        >
          {entityId}
        </button>
      );
    } else {
      parts.push(
        <VinChatLink key={`${vin}-${match.index}`} vin={vin} onOpenEntity={onOpenEntity} />
      );
    }

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return <span className="whitespace-pre-wrap">{parts}</span>;
}
