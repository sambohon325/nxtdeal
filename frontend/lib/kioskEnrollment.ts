import type { KioskGrant } from "./restrictedKiosk";

/** Unmounted enrollment boundary. Caller must supply a fresh interactive sign-in
 * for every operation, including MFA; never pass a cached staff-session accessor.
 * This contract is not server-side proof of authentication freshness. */
export type KioskAuthentication = (signal: AbortSignal) => Promise<string | null>;
export type KioskManagementResult =
  | { status: "enrolled"; grant: KioskGrant }
  | { status: "revoked" | "denied" | "unconfirmed" | "busy" | "closed" };

export function createKioskEnrollment(apiOrigin: string, authenticate: KioskAuthentication, send: typeof fetch = fetch) {
  const origin = new URL(apiOrigin);
  if (origin.username || origin.password || origin.search || origin.hash || origin.pathname !== "/" ||
      (origin.protocol !== "https:" && !(origin.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(origin.hostname)))) {
    throw new Error("Invalid kiosk API origin");
  }
  let active: AbortController | null = null;
  let closed = false;
  let uncertain = false;
  function close() {
    closed = true;
    active?.abort();
  }
  async function manage(deviceId: string, revoke: boolean): Promise<KioskManagementResult> {
    if (closed) return { status: "closed" };
    if (active) return { status: "busy" };
    if (uncertain) return { status: "unconfirmed" };
    const device = deviceId.trim();
    if (!device || deviceId.length > 128 || /[\x00-\x1f\x7f]/.test(deviceId)) return { status: "denied" };
    const controller = new AbortController();
    active = controller;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let token: string | null = null;
    let dispatched = false;
    const stopped = new Promise<never>((_, reject) => {
      controller.signal.addEventListener("abort", () => reject(new Error("Enrollment stopped")), { once: true });
    });
    try {
      // Interactive authentication has its own bounded window, separate from IO.
      timer = setTimeout(() => controller.abort(), 120_000);
      token = await Promise.race([authenticate(controller.signal), stopped]);
      if (closed || controller.signal.aborted) return { status: "closed" };
      if (!token || typeof token !== "string" || token.startsWith("kiosk_") || /[\r\n]/.test(token)) return { status: "denied" };
      clearTimeout(timer);
      timer = setTimeout(() => controller.abort(), 15_000);
      const receive = async () => {
        dispatched = true;
        const response = await send(`${origin.origin}/kiosk/${revoke ? "revoke" : "enroll"}`, {
          method: "POST", credentials: "omit", cache: "no-store", redirect: "error",
          signal: controller.signal,
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify({ device_id: device }),
        });
        token = null;
        const data = response.status === 401 || response.status === 403 ? null : await response.json();
        return { response, data };
      };
      const { response, data } = await Promise.race([receive(), stopped]);
      if (closed || controller.signal.aborted) return { status: "closed" };
      if (response.status === 401 || response.status === 403) return { status: "denied" };
      if (revoke && response.status === 200 && data?.status === "revoked") return { status: "revoked" };
      if (!revoke && response.status === 201 && data?.action === "lobby:checkin:create" &&
          typeof data.token === "string" && /^kiosk_[A-Za-z0-9_-]{43}$/.test(data.token) &&
          typeof data.expires_at === "number" && Number.isFinite(data.expires_at) &&
          data.expires_at > Date.now() / 1000 && data.expires_at <= Date.now() / 1000 + 1800) {
        return { status: "enrolled", grant: { token: data.token, deviceId: device,
          expiresAt: data.expires_at, apiOrigin: origin.origin } };
      }
      uncertain = true;
      return { status: "unconfirmed" };
    } catch {
      if (closed) return { status: "closed" };
      uncertain = dispatched; // Do not silently retry a possibly-applied rotation/revocation.
      return { status: dispatched ? "unconfirmed" : "denied" };
    } finally {
      token = null;
      clearTimeout(timer);
      active = null;
    }
  }
  return { enroll: (device: string) => manage(device, false), revoke: (device: string) => manage(device, true), close };
}
