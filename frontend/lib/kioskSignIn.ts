import type { KioskAuthentication } from "./kioskEnrollment";

type Credentials = { employeeId: string; password: string };
export type KioskSignInPrompts = {
  credentials: (signal: AbortSignal) => Promise<Credentials | null>;
  mfa: (signal: AbortSignal) => Promise<string | null>;
};

/** Each invocation starts password authentication again. Used only inside the
 * enrollment manager's bounded authentication window. No session storage/renewal. */
export function createKioskSignIn(apiOrigin: string, prompts: KioskSignInPrompts, send: typeof fetch = fetch): KioskAuthentication {
  const origin = new URL(apiOrigin);
  if (origin.username || origin.password || origin.search || origin.hash || origin.pathname !== "/" ||
      (origin.protocol !== "https:" && !(origin.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(origin.hostname)))) {
    throw new Error("Invalid kiosk API origin");
  }
  return async (signal) => {
    let credentials: Credentials | null = null;
    let challenge: string | null = null;
    let code: string | null = null;
    async function post(path: string, body: object) {
      if (signal.aborted) return null;
      const response = await send(`${origin.origin}${path}`, {
        method: "POST", credentials: "omit", cache: "no-store", redirect: "error", signal,
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      if (signal.aborted || !response.ok) return null;
      const data = await response.json();
      return signal.aborted ? null : data;
    }
    try {
      if (signal.aborted) return null;
      credentials = await prompts.credentials(signal);
      if (signal.aborted || !credentials?.employeeId.trim() || !credentials.password) return null;
      let result = await post("/auth/login", { employee_id: credentials.employeeId.trim(), password: credentials.password });
      credentials = null;
      if (signal.aborted || !result || result.error) return null;
      if (result.mfa_required === true) {
        if (typeof result.mfa_challenge_token !== "string" || !result.mfa_challenge_token) return null;
        challenge = result.mfa_challenge_token;
        result = null;
        code = await prompts.mfa(signal);
        if (signal.aborted || !code?.trim()) return null;
        result = await post("/auth/mfa/verify", { mfa_challenge_token: challenge, code: code.trim() });
        challenge = null;
        code = null;
      }
      // Password-change-required users must complete that separate staff flow.
      if (signal.aborted || !result || result.error || result.role !== "ADMIN" ||
          result.mfa_required || result.must_change_password !== false ||
          typeof result.token !== "string" || !result.token || result.token.startsWith("kiosk_") || /[\r\n]/.test(result.token)) return null;
      return result.token;
    } catch {
      return null; // Never display provider errors or reflect passwords/challenges.
    } finally {
      credentials = null;
      challenge = null;
      code = null;
    }
  };
}
