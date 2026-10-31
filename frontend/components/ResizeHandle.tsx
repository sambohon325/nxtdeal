"use client";

// Visible drag-to-resize affordance for the workspace panel's left edge (session 41).
// A wide invisible hit-target (easier to grab than a 1px border) with a thin colored
// bar plus a small grip glyph that highlights on hover/drag so it reads as
// interactive rather than just a static divider.
export function ResizeHandle({
  onMouseDown,
  isDragging,
}: {
  onMouseDown: (e: React.MouseEvent) => void;
  isDragging: boolean;
}) {
  return (
    <div
      onMouseDown={onMouseDown}
      title="Drag to resize"
      className="group absolute left-0 top-0 bottom-0 w-3 -translate-x-1/2 cursor-col-resize z-10 flex items-center justify-center"
    >
      <div
        className={
          isDragging
            ? "w-[3px] h-full bg-[#3FBCC4] transition-colors"
            : "w-[3px] h-full bg-transparent group-hover:bg-[#3FBCC4]/60 transition-colors"
        }
      />
      <div
        className={
          isDragging
            ? "absolute w-[5px] h-10 rounded-full bg-[#3FBCC4] flex flex-col items-center justify-center gap-[3px]"
            : "absolute w-[5px] h-10 rounded-full bg-zinc-700 group-hover:bg-[#3FBCC4] flex flex-col items-center justify-center gap-[3px] transition-colors"
        }
      />
    </div>
  );
}
