"use client";

import { useRef, useState } from "react";
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import { angledClip } from "@/components/BrandAngles";

// Chat file attachment (session 47) -- Sam: "we need to add a +file attachment to the
// main chat, so they can add images, files, etc." Self-contained: picking a file
// immediately uploads it to POST /documents/upload (core/documents.py -- an ordinary
// Document entity in the graph, same shape imports/document_import.py's CSV path
// already establishes), shown as a small chip with its upload status. Deliberately
// decoupled from each page's own sendMessage() logic (different per page, already
// complex) rather than threading attachment state through 4 separate chat-send
// implementations -- the attachment lands in the graph the moment it's picked, it
// doesn't need to ride along with a particular chat message to be useful.
type AttachmentStatus = "uploading" | "done" | "error";

type Attachment = {
  key: string;
  file: File;
  status: AttachmentStatus;
  error?: string;
};

export function ChatAttachmentButton() {
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFiles(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;

    const newAttachments: Attachment[] = Array.from(fileList).map((file) => ({
      key: `${file.name}-${file.size}-${Date.now()}-${Math.random()}`,
      file,
      status: "uploading" as const,
    }));

    setAttachments((prev) => [...prev, ...newAttachments]);

    for (const attachment of newAttachments) {
      uploadOne(attachment);
    }

    if (inputRef.current) inputRef.current.value = "";
  }

  async function uploadOne(attachment: Attachment) {
    try {
      const formData = new FormData();
      formData.append("file", attachment.file);

      const response = await fetch(`${API_BASE}/documents/upload`, {
        method: "POST",
        headers: { ...authHeaders() },
        body: formData,
      });

      const data = await response.json();

      setAttachments((prev) =>
        prev.map((a) =>
          a.key === attachment.key
            ? data.error
              ? { ...a, status: "error", error: data.error }
              : { ...a, status: "done" }
            : a
        )
      );
    } catch {
      setAttachments((prev) =>
        prev.map((a) => (a.key === attachment.key ? { ...a, status: "error", error: "Upload failed" } : a))
      );
    }
  }

  function removeAttachment(key: string) {
    setAttachments((prev) => prev.filter((a) => a.key !== key));
  }

  return (
    <div className="flex flex-col gap-2">
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {attachments.map((a) => (
            <div
              key={a.key}
              className="flex items-center gap-1.5 text-xs bg-zinc-900 border border-zinc-800 rounded-full pl-2.5 pr-1.5 py-1"
            >
              <span className="text-zinc-400 max-w-[140px] truncate">{a.file.name}</span>
              {a.status === "uploading" && <span className="text-zinc-600">…</span>}
              {a.status === "done" && <span className="text-[#3FBCC4]">✓</span>}
              {a.status === "error" && <span className="text-[#EE3C25]" title={a.error}>!</span>}
              <button
                onClick={() => removeAttachment(a.key)}
                className="text-zinc-600 hover:text-white transition ml-0.5"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      <input
        ref={inputRef}
        type="file"
        multiple
        accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.csv,.txt"
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />

      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        title="Attach a file"
        style={angledClip(9)}
        className="w-12 h-12 shrink-0 bg-zinc-900 border border-zinc-800 hover:border-brand-teal transition flex items-center justify-center text-zinc-400 hover:text-white"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M21.44 11.05l-9.19 9.19a5 5 0 01-7.07-7.07l9.19-9.19a3.33 3.33 0 014.71 4.71l-9.2 9.19a1.67 1.67 0 01-2.36-2.36l8.49-8.48" />
        </svg>
      </button>
    </div>
  );
}
