// Keep stored tenant settings and older build-time settings off retired origins.
// Unknown legacy tenants must be configured explicitly, never guessed.
export function canonicalApiUrl(value: string): string {
  const url = new URL(value);
  const replacements: Record<string, string> = {
    "dealer1-api.dealeros.xyz": "api.nxtdeal.app",
    "hub-api.dealeros.xyz": "hub-api.nxtdeal.app",
  };
  const replacement = replacements[url.hostname];
  if (replacement) {
    url.protocol = "https:";
    url.hostname = replacement;
    url.port = "";
    return url.toString().replace(/\/$/, "");
  }
  if (url.hostname === "dealeros.xyz" || url.hostname.endsWith(".dealeros.xyz")) {
    throw new Error("This dealership needs its NXTDeal API address configured.");
  }
  return value.replace(/\/$/, "");
}
