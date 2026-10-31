"use client";

/** Untrusted authored markup gets an opaque origin, no scripts, forms or navigation privileges. */
export function SafeHtmlPreview({ html, title = "HTML preview", className = "" }: {
  html: string; title?: string; className?: string;
}) {
  const policy = "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src https: data:; font-src https:; base-uri 'none'; form-action 'none'; frame-src 'none'; connect-src 'none'";
  const document = `<!doctype html><html><head><meta http-equiv="Content-Security-Policy" content="${policy}"><meta name="referrer" content="no-referrer"></head><body>${html}</body></html>`;
  return <iframe title={title} sandbox="" referrerPolicy="no-referrer" srcDoc={document}
    className={`w-full min-h-80 border-0 bg-white ${className}`} />;
}
