"use client";
import { WorkButton, WorkInput, WorkSelect, WorkTextarea , WorkOverlay} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

import { SafeHtmlPreview } from "@/components/SafeHtmlPreview";

// Mailchimp/Klaviyo-style visual email builder (2026-07-23). Replaces the old split
// palette/field-form/preview builder body inside components/EmailSmsBuilder.tsx with a
// single WYSIWYG surface, mirroring components/WebsiteBuilderCanvas.tsx exactly: a top
// toolbar (subject / preheader / audience / send controls / undo-redo / save), a left
// element library, a center email card of real rendered blocks with click-to-edit
// inline text, and a right inspector for the selected block's full field set.
//
// The email model is the same shape as the website model (a `blocks` array of
// { block_key, fields } instead of a `sections` array), so every mutating action here
// mutates the blocks array client-side and persists the whole array through the
// EXISTING updateTemplate(id, { blocks }) patch API -- the same honest single
// persistence path EmailSmsBuilder already used. Undo/Redo is a purely client-side
// snapshot stack of EmailTemplate objects (the backend has no per-edit revision
// endpoint), same as the website canvas. Every returned EmailTemplate is handed back
// through onTemplateChange so the board's library/selection stays in sync.
//
// Like the website builder, there are deliberately NO CSS/style fields surfaced: the
// TemplateBlock model (lib/emailSms.ts) has none. The inspector edits only the real,
// persisted content fields, with a clearly-marked "Style (coming soon)" placeholder.
import { useEffect, useMemo, useRef, useState, type FocusEvent } from "react";
import {
  createTemplate,
  updateTemplate,
  draftFromWizard,
  previewTemplate,
  fetchMergeFields,
  type EmailTemplate,
  type EmailChannel,
  type TemplateBlock,
  type BlockType,
  type BlockField,
  type MergeField,
  type TemplatePreview,
} from "@/lib/emailSms";
import type { MarketingList } from "@/lib/marketingLists";
import type { CrmData } from "@/lib/marketingCrm";
import AiAssistButton from "@/components/AiAssistButton";
import ImageLibraryPicker from "@/components/ImageLibraryPicker";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const HISTORY_CAP = 30;
const DESKTOP_WIDTH = 600;
const MOBILE_WIDTH = 390;

const isImageField = (k: string) => /image|logo|photo|url/i.test(k) && /image|logo|photo/i.test(k);
const isTextyField = (k: string, type: string) => type === "textarea" || /text|body|heading|title|footer|caption|label/i.test(k);

// Client-side GSM-7 / UCS-2 segmentation, mirroring core/email_templates.py's
// sms_segment_info() -- identical math to the old builder, for instant feedback.
function smsSegmentInfo(body: string) {
  const length = body.length;
  const isGsm7 = [...body].every((c) => c.charCodeAt(0) < 128);
  const singleLimit = isGsm7 ? 160 : 70;
  const multiLimit = isGsm7 ? 153 : 67;
  const segments = length === 0 ? 0 : length <= singleLimit ? 1 : Math.ceil(length / multiLimit);
  return { length, encoding: isGsm7 ? "GSM-7" : "UCS-2 (Unicode)", segments };
}

function Btn({
  theme,
  onClick,
  children,
  kind = "default",
  disabled,
  small,
  title,
  active,
}: {
  theme: Theme;
  onClick?: () => void;
  children: React.ReactNode;
  kind?: "default" | "primary" | "danger";
  disabled?: boolean;
  small?: boolean;
  title?: string;
  active?: boolean;
}) {
  return (
    <WorkButton type="submit"
      onClick={onClick}
      disabled={disabled}
      title={title}
      variant={kind === "default" ? "secondary" : kind}
      aria-pressed={active}
    >
      {children}
    </WorkButton>
  );
}

// Icon-button for the per-block floating toolbar (mirrors the website canvas).
function IconBtn({
  onClick,
  disabled,
  title,
  danger,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  title: string;
  danger?: boolean;
  children: React.ReactNode;
}) {
  return (
    <WorkButton type="submit"
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      disabled={disabled}
      title={title}
      className={`w-7 h-7 flex items-center justify-center rounded text-xs shadow-sm transition disabled:opacity-30 disabled:cursor-not-allowed ${
        danger ? "bg-red-900/90 text-red-200 hover:bg-red-800" : "bg-zinc-900/90 text-zinc-200 hover:bg-zinc-700 border border-white/10"
      }`}
    >
      {children}
    </WorkButton>
  );
}

// Inline-editable text node, mirroring SiteSectionRenderer's ecProps: contentEditable
// in edit mode, reporting on blur only when the text actually changed.
const EDIT_CLS = "outline-none rounded-sm cursor-text transition hover:bg-teal-400/5 focus:bg-teal-400/10 focus:ring-2 focus:ring-teal-400";
function ecProps(editable: boolean, field: string, value: string, onEdit: (k: string, v: string) => void) {
  if (!editable) return {};
  return {
    "data-field": field,
    contentEditable: true,
    suppressContentEditableWarning: true,
    spellCheck: false,
    onBlur: (e: FocusEvent<HTMLElement>) => {
      const next = (e.currentTarget.innerText ?? "").replace(/\n$/, "");
      if (next !== value) onEdit(field, next);
    },
  };
}

// Real, VISUAL rendering of a single email block (heading, paragraph, image, button,
// divider, spacer, footer) inside the 600px email card -- the same block_keys
// core/email_templates.py's render_email_html() knows. Unknown/custom block_keys
// (e.g. a future product/vehicle card or social links block added to the catalog)
// fall back to a labelled field dump so nothing is silently dropped.
function EmailBlockView({
  block,
  editable,
  onFieldEdit,
}: {
  block: TemplateBlock;
  editable: boolean;
  onFieldEdit: (key: string, value: string) => void;
}) {
  const f = block.fields ?? {};
  const s = (k: string) => String(f[k] ?? "");

  switch (block.block_key) {
    case "heading": {
      const text = s("text");
      return (
        <h2 {...ecProps(editable, "text", text, onFieldEdit)} className={`text-2xl font-bold text-zinc-900 my-3 min-h-[1em] ${editable ? EDIT_CLS : ""}`}>
          {text || (editable ? "" : "Heading")}
        </h2>
      );
    }
    case "paragraph": {
      const text = s("text");
      return (
        <p {...ecProps(editable, "text", text, onFieldEdit)} className={`text-sm leading-relaxed text-zinc-700 my-3 whitespace-pre-wrap min-h-[1em] ${editable ? EDIT_CLS : ""}`}>
          {text}
        </p>
      );
    }
    case "image": {
      const url = s("image_url");
      const alt = s("alt_text");
      return url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt={alt} className="max-w-full block my-3" onError={(e) => ((e.target as HTMLImageElement).style.opacity = "0.3")} />
      ) : (
        <div className="my-3 aspect-[3/1] rounded bg-zinc-100 border border-dashed border-zinc-300 flex items-center justify-center text-zinc-400 text-sm">
          🖼 Add an image URL in the inspector
        </div>
      );
    }
    case "button": {
      const text = s("text") || "Shop Now";
      return (
        <div className="my-4">
          <span
            {...ecProps(editable, "text", s("text"), onFieldEdit)}
            className={`inline-block bg-[#2B68AB] text-white px-5 py-2.5 rounded-md text-sm font-semibold ${editable ? EDIT_CLS : ""}`}
          >
            {text}
          </span>
        </div>
      );
    }
    case "html": {
      // Raw HTML drop-in -- rendered verbatim (edited via the inspector textarea,
      // never inline-contentEditable, since it's markup not prose).
      const html = s("html");
      return html ? (
        <SafeHtmlPreview className="my-3" html={html} />
      ) : (
        <div className="my-3 rounded bg-zinc-100 border border-dashed border-zinc-300 p-4 text-center text-zinc-400 text-sm">
          {"</>"} Paste your HTML in the inspector
        </div>
      );
    }
    case "divider":
      return <hr className="border-0 border-t border-zinc-200 my-4" />;
    case "spacer":
      return <div style={{ height: `${Number(s("height") || "24") || 24}px` }} />;
    case "footer": {
      const text = s("text");
      return (
        <p {...ecProps(editable, "text", text, onFieldEdit)} className={`mt-6 pt-4 border-t border-zinc-100 text-xs leading-snug text-zinc-400 whitespace-pre-wrap min-h-[1em] ${editable ? EDIT_CLS : ""}`}>
          {text}
        </p>
      );
    }
    default: {
      // Generic fallback for any block_key without a bespoke renderer.
      const entries = Object.entries(f);
      return (
        <div className="my-3 rounded border border-dashed border-zinc-300 bg-zinc-50 p-3 text-left">
          <div className="text-xs uppercase tracking-wide text-zinc-400 mb-1">{block.block_key}</div>
          {entries.length === 0 ? (
            <div className="text-xs text-zinc-400">Set this block&apos;s fields in the inspector.</div>
          ) : (
            entries.map(([k, v]) => (
              <div key={k} className="text-xs text-zinc-600">
                <span className="text-zinc-400">{k}:</span> {String(v ?? "")}
              </div>
            ))
          )}
        </div>
      );
    }
  }
}

export function EmailBuilderCanvas({
  theme = "dark",
  template,
  channel,
  blockCatalog,
  lists,
  crmData,
  abCandidates,
  onTemplateChange,
  onChannelChange,
  onLaunch,
}: {
  theme?: Theme;
  template: EmailTemplate | null;
  channel: EmailChannel;
  blockCatalog: BlockType[];
  lists: MarketingList[];
  crmData: CrmData | null;
  abCandidates: EmailTemplate[];
  onTemplateChange: (t: EmailTemplate) => void;
  onChannelChange: (c: EmailChannel) => void;
  onLaunch: (input: { campaign_type: string; params: Record<string, unknown>; label: string; abVariantBTemplateId?: string }) => void;
}) {
  // ---- Step 1 (setup) form state -----------------------------------------------
  const [setupName, setSetupName] = useState("");
  const [setupSubject, setSetupSubject] = useState("");
  const [setupPreheader, setSetupPreheader] = useState("");
  const [aiGoal, setAiGoal] = useState("");
  const [aiAudience, setAiAudience] = useState("");
  const [aiTone, setAiTone] = useState("friendly and professional");
  const [creating, setCreating] = useState(false);

  // ---- Canvas state ------------------------------------------------------------
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  // Shared media library picker -- holds the field key we're picking an image for.
  const [libFor, setLibFor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const [past, setPast] = useState<EmailTemplate[]>([]);
  const [future, setFuture] = useState<EmailTemplate[]>([]);

  const [draggingKey, setDraggingKey] = useState<string | null>(null);
  const [dropIndex, setDropIndex] = useState<number | null>(null);

  // Top-bar working copies (persist on blur, seeded per template id).
  const [subject, setSubject] = useState("");
  const [preheader, setPreheader] = useState("");
  const [name, setName] = useState("");
  const [listId, setListId] = useState("");

  // Inspector working copy of the selected block's fields (committed on blur).
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [mergeOpenFor, setMergeOpenFor] = useState<string | null>(null);
  const [mergeFields, setMergeFields] = useState<MergeField[]>([]);

  // Preview + send + AI-rewrite overlays.
  const [preview, setPreview] = useState<TemplatePreview | null>(null);
  const [previewDevice, setPreviewDevice] = useState<"desktop" | "mobile">("desktop");
  const [previewNote, setPreviewNote] = useState<string | null>(null);
  const [sendOpen, setSendOpen] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);

  // SMS working copy (debounced persist).
  const [smsDraft, setSmsDraft] = useState("");
  const smsTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const blockByKey = useMemo(() => {
    const m = new Map<string, BlockType>();
    blockCatalog.forEach((b) => m.set(b.key, b));
    return m;
  }, [blockCatalog]);

  const blocks = template?.blocks ?? [];
  const selected = selectedIndex != null ? blocks[selectedIndex] ?? null : null;
  const selectedType = selected ? blockByKey.get(selected.block_key) : undefined;

  useEffect(() => {
    fetchMergeFields().then(setMergeFields).catch(() => {});
  }, []);

  // New template selected/loaded: reset history, seed top-bar + SMS working copies.
  useEffect(() => {
    setPast([]);
    setFuture([]);
    setSelectedIndex(null);
    setName(template?.name ?? "");
    setSubject(template?.subject ?? "");
    setPreheader(template?.preheader ?? "");
    setSmsDraft(template?.sms_body ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [template?.id]);

  // Re-seed the inspector draft whenever the selection or persisted content changes.
  useEffect(() => {
    if (selected && selectedType) {
      setDraft(Object.fromEntries(selectedType.fields.map((f) => [f.key, String(selected.fields[f.key] ?? "")])));
    } else {
      setDraft({});
    }
    setMergeOpenFor(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedIndex, template]);

  // --- Persistence core: patch the template, snapshot into history, propagate ----
  async function persist(patch: Partial<EmailTemplate>, snapshot = true): Promise<EmailTemplate | null> {
    if (!template) return null;
    const snap = template;
    setBusy(true);
    setError(null);
    try {
      const updated = await updateTemplate(template.id, patch);
      if (snapshot) {
        setPast((p) => [...p, snap].slice(-HISTORY_CAP));
        setFuture([]);
      }
      onTemplateChange(updated);
      return updated;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save that change.");
      return null;
    } finally {
      setBusy(false);
    }
  }

  function defaultFieldsFor(blockKey: string): Record<string, unknown> {
    const t = blockByKey.get(blockKey);
    const fields: Record<string, unknown> = {};
    (t?.fields ?? []).forEach((f) => {
      if (f.default !== undefined) fields[f.key] = f.default;
    });
    return fields;
  }

  async function insertBlock(blockKey: string, at?: number) {
    if (!template) return;
    const target = at ?? (selectedIndex != null ? selectedIndex + 1 : blocks.length);
    const next = [...blocks];
    next.splice(target, 0, { block_key: blockKey, fields: defaultFieldsFor(blockKey) });
    const updated = await persist({ blocks: next });
    if (updated) setSelectedIndex(Math.min(target, updated.blocks.length - 1));
  }

  async function duplicateBlock(index: number) {
    const b = blocks[index];
    if (!b) return;
    const next = [...blocks];
    next.splice(index + 1, 0, { block_key: b.block_key, fields: { ...b.fields } });
    const updated = await persist({ blocks: next });
    if (updated) setSelectedIndex(index + 1);
  }

  async function moveBlock(index: number, dir: -1 | 1) {
    const target = index + dir;
    if (target < 0 || target >= blocks.length) return;
    const next = [...blocks];
    const [moved] = next.splice(index, 1);
    next.splice(target, 0, moved);
    const updated = await persist({ blocks: next });
    if (updated) setSelectedIndex(target);
  }

  async function deleteBlock(index: number) {
    const next = blocks.filter((_, i) => i !== index);
    const updated = await persist({ blocks: next });
    if (updated) setSelectedIndex(null);
  }

  async function editBlockField(index: number, key: string, value: string) {
    const b = blocks[index];
    if (!b) return;
    if (String(b.fields[key] ?? "") === value) return;
    const next = blocks.map((bl, i) => (i === index ? { ...bl, fields: { ...bl.fields, [key]: value } } : bl));
    await persist({ blocks: next });
  }

  function insertMergeField(fieldKey: string, tag: string) {
    setDraft((d) => ({ ...d, [fieldKey]: `${d[fieldKey] ?? ""}${tag}` }));
    setMergeOpenFor(null);
  }

  // Undo/Redo: client snapshot stack; each step re-persists so the backend matches.
  async function undo() {
    if (past.length === 0 || !template) return;
    const prev = past[past.length - 1];
    setPast((p) => p.slice(0, -1));
    setFuture((fu) => [template, ...fu].slice(0, HISTORY_CAP));
    setSelectedIndex(null);
    await persist({ blocks: prev.blocks, subject: prev.subject, preheader: prev.preheader, sms_body: prev.sms_body }, false);
  }

  async function redo() {
    if (future.length === 0 || !template) return;
    const next = future[0];
    setFuture((fu) => fu.slice(1));
    setPast((p) => [...p, template].slice(-HISTORY_CAP));
    setSelectedIndex(null);
    await persist({ blocks: next.blocks, subject: next.subject, preheader: next.preheader, sms_body: next.sms_body }, false);
  }

  async function save() {
    if (!template) return;
    const updated = await persist(
      { name, subject, preheader, blocks: template.blocks, sms_body: template.sms_body },
      false
    );
    if (updated) {
      setSaved(true);
      setTimeout(() => setSaved(false), 1600);
    }
  }

  // ---- Step 1: create a blank template, or draft one with the AI wizard ---------
  async function continueBlank() {
    setCreating(true);
    setError(null);
    try {
      const created = await createTemplate(channel, setupName || (channel === "sms" ? "New Text Message" : "New Email"));
      const patch: Partial<EmailTemplate> = {};
      if (setupSubject) patch.subject = setupSubject;
      if (setupPreheader) patch.preheader = setupPreheader;
      const final = Object.keys(patch).length ? await updateTemplate(created.id, patch) : created;
      onTemplateChange(final);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't start a new message.");
    } finally {
      setCreating(false);
    }
  }

  async function runAi(rewrite: boolean) {
    setCreating(true);
    setError(null);
    try {
      const drafted = await draftFromWizard({ channel, goal: aiGoal, audience_description: aiAudience, tone: aiTone });
      if (rewrite && template) {
        // Rewrite the CURRENT template in place with the AI-generated content (keeps
        // the same id/campaign link) rather than spawning a second template.
        const updated = await persist(
          { blocks: drafted.blocks, subject: drafted.subject, preheader: drafted.preheader, sms_body: drafted.sms_body },
          true
        );
        if (updated) setAiOpen(false);
      } else {
        onTemplateChange(drafted);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't reach the AI wizard.");
    } finally {
      setCreating(false);
    }
  }

  async function openPreview(note?: string) {
    if (!template) return;
    setBusy(true);
    setError(null);
    setPreviewNote(note ?? null);
    try {
      setPreview(await previewTemplate(template.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't render a preview.");
    } finally {
      setBusy(false);
    }
  }

  // SMS: debounced persist of the phone-style body editor.
  function onSmsChange(v: string) {
    setSmsDraft(v);
    if (smsTimer.current) clearTimeout(smsTimer.current);
    smsTimer.current = setTimeout(() => {
      persist({ sms_body: v });
    }, 600);
  }

  // Keyboard undo/redo -- never hijack native undo while typing in a field.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement | null;
      if (el && (el.isContentEditable || el.tagName === "INPUT" || el.tagName === "TEXTAREA")) return;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) redo();
        else undo();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [past, future, template]);

  const panelBorder = tc(theme, "border-zinc-800", "border-zinc-200");
  const panelBg = tc(theme, "bg-brand-charcoal", "bg-white");
  const inputCls = tc(theme, "bg-zinc-900 border border-zinc-700 text-white", "bg-white border border-zinc-300 text-black");

  // ============================================================================
  // STEP 1 -- Campaign Setup & AI prompt (shown whenever no template is loaded).
  // ============================================================================
  if (!template) {
    return (
      <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
        <div className="mx-auto w-full max-w-xl p-6 space-y-4">
          <div className="flex items-center gap-2 text-xs font-semibold">
            <span className="w-6 h-6 rounded-full bg-brand-teal text-black flex items-center justify-center">1</span>
            <span>Campaign Setup</span>
            <span className="mx-1 text-zinc-600">→</span>
            <span className="w-6 h-6 rounded-full bg-zinc-700 text-zinc-300 flex items-center justify-center">2</span>
            <span className="text-zinc-500">Design</span>
          </div>

          {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}

          <div className={`rounded-lg border p-4 space-y-3 ${panelBorder} ${panelBg}`}>
            <div className="flex rounded-md border overflow-hidden w-max text-xs">
              {(["email", "sms"] as const).map((c) => (
                <WorkButton type="submit"
                  key={c}
                  onClick={() => onChannelChange(c)}
                  className={`px-3 py-1 ${channel === c ? "bg-brand-teal text-black font-semibold" : tc(theme, "bg-zinc-900 text-zinc-400", "bg-zinc-100 text-zinc-600")}`}
                >
                  {c === "email" ? "✉ Email" : "💬 SMS"}
                </WorkButton>
              ))}
            </div>

            <label className="block">
              <span className="text-xs text-zinc-500">Name (internal)</span>
              <WorkInput value={setupName} onChange={(e) => setSetupName(e.target.value)} placeholder="e.g. Spring Service Special" className={`w-full h-8 mt-0.5 px-2 text-xs rounded ${inputCls}`} />
            </label>
            {channel === "email" && (
              <>
                <label className="block">
                  <span className="text-xs text-zinc-500">Subject line</span>
                  <WorkInput value={setupSubject} onChange={(e) => setSetupSubject(e.target.value)} className={`w-full h-8 mt-0.5 px-2 text-xs rounded ${inputCls}`} />
                </label>
                <label className="block">
                  <span className="text-xs text-zinc-500">Preheader (preview text)</span>
                  <WorkInput value={setupPreheader} onChange={(e) => setSetupPreheader(e.target.value)} className={`w-full h-8 mt-0.5 px-2 text-xs rounded ${inputCls}`} />
                </label>
              </>
            )}
            <Btn theme={theme} kind="primary" onClick={continueBlank} disabled={creating}>
              {creating ? "Starting…" : "Continue to Design →"}
            </Btn>
          </div>

          <div className={`rounded-lg border p-4 space-y-3 ${panelBorder} ${panelBg}`}>
            <div className="text-xs font-bold">✨ Or let AI draft it for you</div>
            <label className="block">
              <span className="text-xs text-zinc-500">Goal</span>
              <WorkInput value={aiGoal} onChange={(e) => setAiGoal(e.target.value)} placeholder="e.g. remind customers about a spring service special" className={`w-full h-8 mt-0.5 px-2 text-xs rounded ${inputCls}`} />
            </label>
            <label className="block">
              <span className="text-xs text-zinc-500">Audience</span>
              <WorkInput value={aiAudience} onChange={(e) => setAiAudience(e.target.value)} placeholder="e.g. customers overdue for service" className={`w-full h-8 mt-0.5 px-2 text-xs rounded ${inputCls}`} />
            </label>
            <label className="block">
              <span className="text-xs text-zinc-500">Tone</span>
              <WorkInput value={aiTone} onChange={(e) => setAiTone(e.target.value)} className={`w-full h-8 mt-0.5 px-2 text-xs rounded ${inputCls}`} />
            </label>
            <Btn theme={theme} onClick={() => runAi(false)} disabled={creating}>
              {creating ? "Drafting…" : "Generate Draft & Design →"}
            </Btn>
            <div className="text-xs text-zinc-600">Generates a real draft, then drops you into the visual editor to refine it.</div>
          </div>
        </div>
      </div>
    );
  }

  // ============================================================================
  // STEP 2 -- The full visual canvas.
  // ============================================================================
  const isSms = template.channel === "sms";
  const seg = smsDraft ? smsSegmentInfo(smsDraft) : null;

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white", "flex-1 flex flex-col min-h-0 bg-white text-black")}>
      {/* ---- Top toolbar -------------------------------------------------------- */}
      <div className={`flex flex-col gap-2 px-4 py-2 border-b shrink-0 ${panelBorder}`}>
        <div className="flex items-center gap-2 flex-wrap">
          <WorkField label="Message name"><WorkInput
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => name !== (template.name ?? "") && persist({ name })}
            placeholder="Message name"
            className={`h-7 px-2 text-xs rounded w-40 ${inputCls}`}
          /></WorkField>
          {!isSms && (
            <>
              <WorkField label="Subject line"><WorkInput
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                onBlur={() => subject !== (template.subject ?? "") && persist({ subject })}
                placeholder="Subject line"
                className={`h-7 px-2 text-xs font-semibold rounded flex-1 min-w-[160px] ${inputCls}`}
              /></WorkField>
              <WorkField label="Preheader (preview text)"><WorkInput
                value={preheader}
                onChange={(e) => setPreheader(e.target.value)}
                onBlur={() => preheader !== (template.preheader ?? "") && persist({ preheader })}
                placeholder="Preheader (preview text)"
                className={`h-7 px-2 text-xs rounded flex-1 min-w-[140px] ${tc(theme, "bg-zinc-900 border border-zinc-700 text-zinc-400", "bg-white border border-zinc-300 text-zinc-500")}`}
              /></WorkField>
            </>
          )}

          {/* Audience / List selector */}
          <WorkField label="List ID"><WorkSelect value={listId} onChange={(e) => setListId(e.target.value)} className={`h-7 px-2 text-xs rounded ${inputCls}`} title="Audience list">
            <option value="">Audience: choose a list…</option>
            {lists.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name} ({l.member_ids?.length ?? 0})
              </option>
            ))}
          </WorkSelect></WorkField>
        </div>

        <div className="flex items-center gap-1.5 flex-wrap">
          <div className="flex items-center gap-1">
            <Btn theme={theme} small onClick={undo} disabled={past.length === 0} title="Undo (⌘Z)">↶ Undo</Btn>
            <Btn theme={theme} small onClick={redo} disabled={future.length === 0} title="Redo (⇧⌘Z)">↷ Redo</Btn>
          </div>
          <div className="ml-auto flex items-center gap-1.5">
            {error && <span className="text-xs text-red-400 max-w-[200px] truncate" title={error}>{error}</span>}
            {busy && <span className="text-xs text-zinc-500">Working…</span>}
            {saved && <span className="text-xs text-green-400 font-medium animate-pulse">Saved ✓</span>}
            <Btn theme={theme} small onClick={() => openPreview()} disabled={busy}>👁 Preview</Btn>
            <Btn theme={theme} small onClick={() => openPreview("Test send: no transactional email endpoint is wired yet — this is exactly what the recipient would receive. TODO: point at a real /send-test route once it exists.")} disabled={busy}>
              ✉ Send Test
            </Btn>
            <Btn theme={theme} small kind="primary" onClick={() => setSendOpen(true)}>🚀 Schedule / Send</Btn>
            <Btn theme={theme} small onClick={save} disabled={busy}>💾 Save</Btn>
          </div>
        </div>
      </div>

      {/* ---- 3-column shell (email) OR single SMS editor ------------------------ */}
      {isSms ? (
        <div className={`flex-1 overflow-auto flex justify-center py-8 px-4 ${tc(theme, "bg-zinc-950/60", "bg-zinc-100")}`}>
          <div className="w-full max-w-sm space-y-3">
            <div className="flex items-center justify-between">
              <div className="text-xs uppercase tracking-wide text-zinc-500">Text message</div>
              <AiAssistButton
                theme={theme}
                value={smsDraft}
                context="SMS text message to a dealership customer (keep it short)"
                fieldLabel="text message"
                onApply={(text, mode) => onSmsChange(mode === "insert" ? `${smsDraft}${text}` : text)}
              />
            </div>
            <div className="rounded-[2rem] border-4 border-zinc-800 bg-zinc-900 p-4 shadow-2xl">
              <div className="text-xs text-zinc-500 text-center mb-3">Your Dealership</div>
              <div className="min-h-[120px] flex items-end">
                <div className="max-w-[85%] bg-brand-teal text-black text-sm rounded-2xl rounded-bl-sm px-3 py-2 whitespace-pre-wrap break-words">
                  {smsDraft || "Type your message below…"}
                </div>
              </div>
            </div>
            <WorkField label="Type your text message"><WorkTextarea
              value={smsDraft}
              onChange={(e) => onSmsChange(e.target.value)}
              rows={5}
              placeholder="Type your text message…"
              className={`w-full px-3 py-2 text-sm rounded resize-none ${inputCls}`}
            /></WorkField>
            {seg && (
              <div className="text-xs text-zinc-500 flex items-center gap-3">
                <span>{seg.length} chars</span>
                <span>{seg.encoding}</span>
                <span className="font-semibold">{seg.segments} segment{seg.segments === 1 ? "" : "s"}</span>
              </div>
            )}
            <div className="text-xs text-zinc-600">
              Merge fields: {mergeFields.map((f) => `{{${f.key}}}`).join("  ")}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex min-h-0">
          {/* Left: element library */}
          <div className={`w-52 shrink-0 border-r flex flex-col ${panelBorder}`}>
            <div className={`px-3 py-2 text-xs font-semibold uppercase tracking-wide text-zinc-500 border-b ${panelBorder}`}>Elements</div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
              {blockCatalog.map((b) => (
                <div
                  key={b.key}
                  draggable
                  onDragStart={(e) => {
                    setDraggingKey(b.key);
                    e.dataTransfer.setData("text/plain", b.key);
                    e.dataTransfer.effectAllowed = "copy";
                  }}
                  onDragEnd={() => {
                    setDraggingKey(null);
                    setDropIndex(null);
                  }}
                  onClick={() => insertBlock(b.key)}
                  className={`rounded-lg border p-2 cursor-grab active:cursor-grabbing hover:border-brand-teal transition ${panelBorder} ${panelBg}`}
                  title="Click to append, or drag onto the canvas"
                >
                  <div className="text-xs font-semibold flex items-center gap-1">
                    <span className="text-zinc-500">⠿</span>
                    {b.name}
                  </div>
                  {b.description && <div className="text-xs text-zinc-500 mt-0.5 leading-snug">{b.description}</div>}
                </div>
              ))}
              {blockCatalog.length === 0 && <div className="text-xs text-zinc-500 px-1">Loading elements…</div>}
            </div>
          </div>

          {/* Center: the email card */}
          <div className={`flex-1 overflow-auto flex justify-center py-6 px-4 ${tc(theme, "bg-zinc-950/60", "bg-zinc-100")}`} onClick={() => setSelectedIndex(null)}>
            <div className="bg-white shadow-2xl self-start rounded" style={{ width: DESKTOP_WIDTH, maxWidth: "100%" }}>
              {blocks.length === 0 ? (
                <div
                  onDragOver={(e) => {
                    if (!draggingKey) return;
                    e.preventDefault();
                    setDropIndex(0);
                  }}
                  onDrop={(e) => {
                    if (!draggingKey) return;
                    e.preventDefault();
                    const key = draggingKey;
                    setDraggingKey(null);
                    setDropIndex(null);
                    insertBlock(key, 0);
                  }}
                  className="py-24 px-6 text-center text-sm text-zinc-400"
                >
                  This email is empty. Click an element on the left to add one — or drag it here.
                </div>
              ) : (
                <div className="px-6 py-6">
                  {blocks.map((b, i) => {
                    const isSel = selectedIndex === i;
                    return (
                      <div
                        key={i}
                        className={`group relative ${isSel ? "ring-2 ring-brand-teal ring-inset z-10" : "hover:ring-2 hover:ring-brand-teal/40 hover:ring-inset"}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedIndex(i);
                        }}
                        onDragOver={(e) => {
                          if (!draggingKey) return;
                          e.preventDefault();
                          const rect = e.currentTarget.getBoundingClientRect();
                          const before = e.clientY < rect.top + rect.height / 2;
                          setDropIndex(before ? i : i + 1);
                        }}
                        onDrop={(e) => {
                          if (!draggingKey) return;
                          e.preventDefault();
                          const at = dropIndex ?? i;
                          const key = draggingKey;
                          setDraggingKey(null);
                          setDropIndex(null);
                          insertBlock(key, at);
                        }}
                      >
                        {dropIndex === i && <div className="absolute left-0 right-0 top-0 h-1 bg-brand-teal z-30" />}
                        {dropIndex === i + 1 && <div className="absolute left-0 right-0 bottom-0 h-1 bg-brand-teal z-30" />}

                        <div className={`absolute -top-1 left-0 z-20 ${isSel ? "opacity-100" : "opacity-0 group-hover:opacity-100"} transition`}>
                          <span className="text-xs px-1.5 py-0.5 rounded bg-zinc-900/90 text-zinc-300 border border-white/10">
                            {blockByKey.get(b.block_key)?.name ?? b.block_key}
                          </span>
                        </div>

                        <div className={`absolute -top-1 right-0 z-20 flex items-center gap-1 ${isSel ? "opacity-100" : "opacity-0 group-hover:opacity-100"} transition`}>
                          <IconBtn onClick={() => moveBlock(i, -1)} disabled={busy || i === 0} title="Move up">↑</IconBtn>
                          <IconBtn onClick={() => moveBlock(i, 1)} disabled={busy || i === blocks.length - 1} title="Move down">↓</IconBtn>
                          <IconBtn onClick={() => duplicateBlock(i)} disabled={busy} title="Duplicate">⧉</IconBtn>
                          <IconBtn onClick={() => { setSelectedIndex(i); setAiOpen(true); }} disabled={busy} title="AI Rewrite">✨</IconBtn>
                          <IconBtn onClick={() => deleteBlock(i)} disabled={busy} title="Delete" danger>✕</IconBtn>
                        </div>

                        <EmailBlockView block={b} editable onFieldEdit={(key, value) => editBlockField(i, key, value)} />
                      </div>
                    );
                  })}
                  <div
                    onDragOver={(e) => {
                      if (!draggingKey) return;
                      e.preventDefault();
                      setDropIndex(blocks.length);
                    }}
                    onDrop={(e) => {
                      if (!draggingKey) return;
                      e.preventDefault();
                      const key = draggingKey;
                      setDraggingKey(null);
                      setDropIndex(null);
                      insertBlock(key, blocks.length);
                    }}
                    className={`h-6 ${dropIndex === blocks.length ? "bg-brand-teal/30" : ""}`}
                  />
                </div>
              )}
            </div>
          </div>

          {/* Right: inspector */}
          {inspectorOpen ? (
            <div className={`w-80 shrink-0 border-l flex flex-col ${panelBorder}`}>
              <div className={`flex items-center justify-between px-3 py-2 border-b ${panelBorder}`}>
                <div className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Inspector</div>
                <WorkButton type="submit" onClick={() => setInspectorOpen(false)} title="Collapse" className="text-zinc-500 hover:text-white text-xs">→│</WorkButton>
              </div>
              <div className="flex-1 overflow-y-auto p-3 space-y-3">
                {!selected || !selectedType ? (
                  <div className="text-center text-zinc-500 pt-10 px-4 space-y-2">
                    <div className="text-3xl">🎯</div>
                    <div className="text-sm font-medium">Nothing selected</div>
                    <div className="text-xs">Click any block on the canvas to edit its content here, or add one from the left.</div>
                  </div>
                ) : (
                  <>
                    <div className="text-sm font-semibold">{selectedType.name}</div>
                    {selectedType.fields.length === 0 && <div className="text-xs text-zinc-500">This block has no editable content.</div>}

                    {selectedType.fields.map((f: BlockField) => (
                      <div key={f.key} className="space-y-1">
                        <div className="flex items-center justify-between gap-2">
                          <div className="text-xs text-zinc-500">{f.label}</div>
                          {isTextyField(f.key, f.type) && (
                            <AiAssistButton
                              theme={theme}
                              aria-label={f.label} value={draft[f.key] ?? ""}
                              context={f.label}
                              fieldLabel={f.label}
                              onApply={(text, mode) => {
                                const next = mode === "insert" ? `${draft[f.key] ?? ""}${text}` : text;
                                setDraft((d) => ({ ...d, [f.key]: next }));
                                if (selectedIndex != null) editBlockField(selectedIndex, f.key, next);
                              }}
                            />
                          )}
                        </div>
                        {f.type === "textarea" ? (
                          <WorkTextarea
                            aria-label={f.label} value={draft[f.key] ?? ""}
                            onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                            onBlur={() => selectedIndex != null && editBlockField(selectedIndex, f.key, draft[f.key] ?? "")}
                            rows={3}
                            className={`w-full text-xs rounded px-2 py-1.5 ${inputCls}`}
                          />
                        ) : (
                          <WorkInput
                            aria-label={f.label} value={draft[f.key] ?? ""}
                            onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                            onBlur={() => selectedIndex != null && editBlockField(selectedIndex, f.key, draft[f.key] ?? "")}
                            className={`w-full text-xs rounded px-2 py-1.5 ${inputCls}`}
                          />
                        )}

                        {isImageField(f.key) && (
                          <WorkButton type="submit"
                            onClick={() => setLibFor(f.key)}
                            className="text-xs text-brand-teal hover:underline"
                          >
                            🖼 Pick from shared library
                          </WorkButton>
                        )}

                        {isImageField(f.key) && draft[f.key] && (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={draft[f.key]} alt="" className="w-full h-20 object-cover rounded border border-zinc-700" onError={(e) => ((e.target as HTMLImageElement).style.display = "none")} />
                        )}

                        {/* Merge-field insertion for text-ish fields. */}
                        {isTextyField(f.key, f.type) && mergeFields.length > 0 && (
                          <div>
                            <WorkButton type="submit" onClick={() => setMergeOpenFor((p) => (p === f.key ? null : f.key))} className="text-xs text-brand-teal hover:underline">
                              {mergeOpenFor === f.key ? "Close merge tags" : "{ } Insert merge field"}
                            </WorkButton>
                            {mergeOpenFor === f.key && (
                              <div className="mt-1 flex flex-wrap gap-1 rounded border border-zinc-700 p-1.5">
                                {mergeFields.map((mf) => (
                                  <WorkButton type="submit"
                                    key={mf.key}
                                    onClick={() => {
                                      insertMergeField(f.key, `{{${mf.key}}}`);
                                      if (selectedIndex != null) editBlockField(selectedIndex, f.key, `${draft[f.key] ?? ""}{{${mf.key}}}`);
                                    }}
                                    title={mf.example}
                                    className="text-xs px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
                                  >
                                    {`{{${mf.key}}}`}
                                  </WorkButton>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    ))}

                    <div className="flex flex-wrap gap-1.5 pt-1">
                      <Btn theme={theme} small onClick={() => setAiOpen(true)} disabled={busy}>✨ AI Rewrite</Btn>
                      <Btn theme={theme} small onClick={() => selectedIndex != null && duplicateBlock(selectedIndex)} disabled={busy}>⧉ Duplicate</Btn>
                      <Btn theme={theme} small kind="danger" onClick={() => selectedIndex != null && deleteBlock(selectedIndex)} disabled={busy}>Delete</Btn>
                    </div>

                    {/* Style (coming soon) -----------------------------------------------
                        The TemplateBlock model (lib/emailSms.ts) has NO style fields, so
                        surfacing padding/color/font controls here would silently drop
                        edits. This placeholder marks where a future style system lands. */}
                    <div className={`mt-3 pt-3 border-t ${panelBorder}`}>
                      <div className="text-xs uppercase tracking-wide text-zinc-600 mb-1">Style (coming soon)</div>
                      <div className="text-xs text-zinc-500 rounded border border-dashed border-zinc-700 px-2 py-3 text-center">
                        Padding, colors &amp; typography controls will live here once the block model supports them.
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          ) : (
            <WorkButton type="submit" onClick={() => setInspectorOpen(true)} title="Open inspector" className={`w-8 shrink-0 border-l flex items-center justify-center text-zinc-500 hover:text-white ${panelBorder}`}>
              │←
            </WorkButton>
          )}
        </div>
      )}

      {/* ---- Preview overlay ---------------------------------------------------- */}
      {preview && (
        <WorkOverlay className="fixed inset-0 z-50 bg-black/70 flex flex-col items-center justify-start p-6 overflow-auto" onClick={() => setPreview(null)}>
          <div className="w-full max-w-3xl flex items-center justify-between mb-3" onClick={(e) => e.stopPropagation()}>
            <div className="flex rounded-md border border-zinc-700 overflow-hidden">
              {(["desktop", "mobile"] as const).map((d) => (
                <WorkButton type="submit" key={d} onClick={() => setPreviewDevice(d)} className={`text-xs px-3 py-1 ${previewDevice === d ? "bg-zinc-200 text-black font-medium" : "bg-zinc-900 text-zinc-400"}`}>
                  {d === "desktop" ? "🖥 Desktop" : "📱 Mobile"}
                </WorkButton>
              ))}
            </div>
            <WorkButton type="submit" onClick={() => setPreview(null)} className="text-white text-sm px-3 py-1 rounded bg-zinc-800 hover:bg-zinc-700">Close ✕</WorkButton>
          </div>
          {previewNote && (
            <div className="w-full max-w-3xl mb-3 text-xs px-3 py-2 rounded bg-amber-500/15 border border-amber-500/40 text-amber-200" onClick={(e) => e.stopPropagation()}>
              {previewNote}
            </div>
          )}
          <div className="bg-white rounded shadow-2xl overflow-hidden" style={{ width: previewDevice === "desktop" ? DESKTOP_WIDTH : MOBILE_WIDTH, maxWidth: "100%" }} onClick={(e) => e.stopPropagation()}>
            {preview.channel === "email" ? (
              <div className="text-black">
                {preview.subject && <div className="px-4 py-2 border-b border-zinc-200 text-sm font-semibold">{preview.subject}</div>}
                <SafeHtmlPreview className="p-2" html={preview.html} />
              </div>
            ) : (
              <div className="p-4">
                <div className="max-w-[85%] bg-brand-teal text-black text-sm rounded-2xl rounded-bl-sm px-3 py-2 whitespace-pre-wrap">{preview.sms_body || "…"}</div>
              </div>
            )}
          </div>
        </WorkOverlay>
      )}

      {/* ---- AI Rewrite overlay (whole-message regenerate via draftFromWizard) --- */}
      {aiOpen && (
        <WorkOverlay className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-6" onClick={() => setAiOpen(false)}>
          <div className={`w-full max-w-md rounded-lg border p-4 space-y-3 ${panelBorder} ${panelBg} ${tc(theme, "text-white", "text-black")}`} onClick={(e) => e.stopPropagation()}>
            <div className="text-sm font-bold">✨ AI Rewrite this {isSms ? "text" : "email"}</div>
            <div className="text-xs text-zinc-500">
              Regenerates the whole message from a fresh prompt and swaps its content in place (the backend has no per-block AI endpoint, so a rewrite is message-level).
            </div>
            <label className="block">
              <span className="text-xs text-zinc-500">Goal</span>
              <WorkInput value={aiGoal} onChange={(e) => setAiGoal(e.target.value)} className={`w-full h-8 mt-0.5 px-2 text-xs rounded ${inputCls}`} />
            </label>
            <label className="block">
              <span className="text-xs text-zinc-500">Audience</span>
              <WorkInput value={aiAudience} onChange={(e) => setAiAudience(e.target.value)} className={`w-full h-8 mt-0.5 px-2 text-xs rounded ${inputCls}`} />
            </label>
            <label className="block">
              <span className="text-xs text-zinc-500">Tone</span>
              <WorkInput value={aiTone} onChange={(e) => setAiTone(e.target.value)} className={`w-full h-8 mt-0.5 px-2 text-xs rounded ${inputCls}`} />
            </label>
            <div className="flex gap-2 justify-end">
              <Btn theme={theme} small onClick={() => setAiOpen(false)}>Cancel</Btn>
              <Btn theme={theme} small kind="primary" onClick={() => runAi(true)} disabled={creating}>{creating ? "Rewriting…" : "Rewrite"}</Btn>
            </div>
          </div>
        </WorkOverlay>
      )}

      {/* ---- Schedule / Send overlay ------------------------------------------- */}
      {sendOpen && (
        <SendPanel
          theme={theme}
          channel={template.channel}
          crmData={crmData}
          lists={lists}
          selectedListId={listId}
          abCandidates={abCandidates}
          onClose={() => setSendOpen(false)}
          onLaunch={(input) => {
            onLaunch(input);
            setSendOpen(false);
          }}
        />
      )}

      <ImageLibraryPicker
        open={libFor !== null}
        onClose={() => setLibFor(null)}
        theme={theme}
        onPick={(url) => {
          const key = libFor;
          if (key) {
            setDraft((d) => ({ ...d, [key]: url }));
            if (selectedIndex != null) editBlockField(selectedIndex, key, url);
          }
          setLibFor(null);
        }}
      />
    </div>
  );
}

// Compact send/schedule popover. The only real "send" path that exists today is the
// CRM campaign flow (createCrmCampaign -> activate from the Campaigns tab), so both
// "Send Now" and "Schedule" create a draft campaign linked to this template via the
// board's onLaunch handler. Audience is a CRM segment type; the top-bar list selector
// is surfaced for context but the campaign endpoint doesn't yet accept a raw list_id
// (TODO: add a send-to-list campaign source), and there is no scheduling endpoint yet
// (TODO), so "Schedule" currently behaves like "Send Now" (creates the draft).
function SendPanel({
  theme,
  channel,
  crmData,
  lists,
  selectedListId,
  abCandidates,
  onClose,
  onLaunch,
}: {
  theme: Theme;
  channel: EmailChannel;
  crmData: CrmData | null;
  lists: MarketingList[];
  selectedListId: string;
  abCandidates: EmailTemplate[];
  onClose: () => void;
  onLaunch: (input: { campaign_type: string; params: Record<string, unknown>; label: string; abVariantBTemplateId?: string }) => void;
}) {
  const types = (crmData?.campaigns.available_types ?? []).filter((t) => t.key !== "individual");
  const [campaignType, setCampaignType] = useState(types[0]?.key ?? "general");
  const [abEnabled, setAbEnabled] = useState(false);
  const [variantBId, setVariantBId] = useState("");
  const selectedList = lists.find((l) => l.id === selectedListId);
  const inputCls = tc(theme, "bg-zinc-900 border border-zinc-700 text-white", "bg-white border border-zinc-300 text-black");
  const panelBg = tc(theme, "bg-brand-charcoal border-zinc-800 text-white", "bg-white border-zinc-200 text-black");

  function launch() {
    const t = types.find((x) => x.key === campaignType);
    onLaunch({
      campaign_type: campaignType,
      params: {},
      label: t?.name ?? campaignType,
      abVariantBTemplateId: abEnabled && variantBId ? variantBId : undefined,
    });
  }

  return (
    <WorkOverlay className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-6" onClick={onClose}>
      <div className={`w-full max-w-md rounded-lg border p-4 space-y-3 ${panelBg}`} onClick={(e) => e.stopPropagation()}>
        <div className="text-sm font-bold">🚀 Schedule / Send ({channel === "sms" ? "SMS" : "Email"})</div>

        <label className="block">
          <span className="text-xs text-zinc-500">Audience segment (from the CRM)</span>
          <WorkSelect value={campaignType} onChange={(e) => setCampaignType(e.target.value)} className={`w-full h-8 mt-0.5 px-2 text-xs rounded ${inputCls}`}>
            {types.map((t) => (
              <option key={t.key} value={t.key}>{t.name}</option>
            ))}
          </WorkSelect>
        </label>

        {selectedList && (
          <div className="text-xs text-zinc-500">
            Top-bar list selected: <span className="text-zinc-300">{selectedList.name}</span> ({selectedList.member_ids?.length ?? 0} members). Note: the campaign send currently uses the CRM segment above — send-to-list is a TODO on the backend.
          </div>
        )}

        {abCandidates.length > 0 && (
          <div className="rounded-md border border-zinc-700 p-2 space-y-1.5">
            <label className="flex items-center gap-1.5 text-xs cursor-pointer">
              <WorkInput type="checkbox" checked={abEnabled} onChange={(e) => setAbEnabled(e.target.checked)} />
              <span>🔀 A/B test against a second message</span>
            </label>
            {abEnabled && (
              <WorkField label="Variant BId"><WorkSelect value={variantBId} onChange={(e) => setVariantBId(e.target.value)} className={`w-full h-7 px-2 text-xs rounded ${inputCls}`}>
                <option value="">Choose Variant B…</option>
                {abCandidates.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </WorkSelect></WorkField>
            )}
          </div>
        )}

        <div className="text-xs text-zinc-500">
          Creates a draft campaign linked to this message — activate it from the CRM&apos;s Campaigns tab. There is no immediate-send or scheduling endpoint yet (TODO), so both buttons create the draft.
        </div>

        <div className="flex gap-2 justify-end">
          <Btn theme={theme} small onClick={onClose}>Cancel</Btn>
          <Btn theme={theme} small onClick={launch}>🕑 Schedule</Btn>
          <Btn theme={theme} small kind="primary" onClick={launch}>Send Now →</Btn>
        </div>
      </div>
    </WorkOverlay>
  );
}
