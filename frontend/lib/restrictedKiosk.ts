/** Ephemeral kiosk-only transport. Never reads staff auth or browser storage. */
export type KioskGrant = { token: string; deviceId: string; expiresAt: number; apiOrigin: string };
export type KioskResult = "confirmed" | "unconfirmed" | "closed" | "busy";
export function createRestrictedKiosk(grant: KioskGrant, send: typeof fetch = fetch) {
  const origin = new URL(grant.apiOrigin);
  if (origin.username || origin.password || origin.search || origin.hash || origin.pathname !== "/" ||
      (origin.protocol !== "https:" && !(origin.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(origin.hostname)))) {
    throw new Error("Invalid kiosk API origin");
  }
  if (!/^kiosk_[A-Za-z0-9_-]{43}$/.test(grant.token) || !grant.deviceId.trim() || !Number.isFinite(grant.expiresAt)) {
    throw new Error("Invalid kiosk grant");
  }
  let token = grant.token;
  let pending: AbortController | null = null;
  let blocked = false;
  let generation = 0;
  function close() {
    generation++;
    token = "";
    blocked = true;
    pending?.abort();
    pending = null;
  }
  async function submit(fields: { name: string; phone: string; reason: string }): Promise<KioskResult> {
    if (!token || Date.now() >= grant.expiresAt * 1000) { close(); return "closed"; }
    if (pending) return "busy";
    if (blocked) return "unconfirmed";
    const revision = generation;
    const controller = new AbortController();
    pending = controller;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    try {
      const requestId = crypto.randomUUID();
      const deadline = new Promise<never>((_, reject) => {
        timeout = setTimeout(() => {
          reject(new Error("Check-in deadline exceeded"));
          controller.abort();
        }, 15_000);
      });
      const receive = async () => {
        const response = await send(`${origin.origin}/kiosk/checkin`, {
          method: "POST", credentials: "omit", cache: "no-store", redirect: "error",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          signal: controller.signal,
          body: JSON.stringify({ name: fields.name, phone: fields.phone, reason: fields.reason,
            device_id: grant.deviceId, request_id: requestId }),
        });
        // The deadline includes the response body, not just arrival of headers.
        const data = response.status === 401 || response.status === 403 ? null : await response.json();
        return { response, data };
      };
      const { response, data } = await Promise.race([receive(), deadline]);
      if (revision !== generation) return "closed";
      if (response.status === 401 || response.status === 403) { close(); return "closed"; }
      if (response.ok && data?.status === "checked_in" && data?.receipt === requestId) return "confirmed";
      blocked = true;
      return "unconfirmed";
    } catch {
      if (revision !== generation) return "closed";
      blocked = true; // A network failure does not prove the server did not write.
      return "unconfirmed";
    } finally {
      clearTimeout(timeout);
      if (pending === controller) pending = null;
    }
  }
  return { submit, close };
}
