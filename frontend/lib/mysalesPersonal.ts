import { HUB_API_BASE } from "./hubApi";
export type PersonalAccount = {
  id: string;
  name: string;
  email: string;
  email_verified: boolean;
};
export type PersonalRecord = {
  id: string;
  title: string;
  notes: string;
  email: string;
  phone: string;
  due: string;
  done: boolean;
  stage: string;
};
export type InventoryConnection = {
  dealer_id: string;
  name: string;
  api_base_url: string;
};
const KEY = "nxtdeal_mysales_personal";
export function personalToken() {
  return typeof window === "undefined" ? "" : sessionStorage.getItem(KEY) || "";
}
export function setPersonalToken(token: string) {
  if (token) sessionStorage.setItem(KEY, token);
  else sessionStorage.removeItem(KEY);
}
export async function personalRequest<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const requestToken = personalToken();
  const res = await fetch(`${HUB_API_BASE}/mysales${path}`, {
    method,
    credentials: "omit",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(requestToken
        ? { Authorization: `Bearer ${requestToken}` }
        : {}),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && requestToken && requestToken === personalToken()) {
      // A delayed failure from a previous session must not sign out a newer login.
      setPersonalToken("");
      if (typeof window !== "undefined")
        window.dispatchEvent(new Event("mysales-session-expired"));
    }
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Please check your entries and try again.",
    );
  }
  return data;
}
export async function personalSignIn(
  mode: "login" | "signup",
  body: { name: string; email: string; password: string },
) {
  const result = await personalRequest<{
    token: string;
    account: PersonalAccount;
  }>(`/${mode}`, "POST", body);
  setPersonalToken(result.token);
  return result.account;
}
export async function personalSignOut() {
  try {
    await personalRequest("/logout", "POST");
  } finally {
    setPersonalToken("");
  }
}
export type RetailVehicle = {
  id: string;
  year: string;
  make: string;
  model: string;
  trim: string;
  price: number | string | null;
  mileage: number | string | null;
  image_url: string | null;
};
export async function personalInventory(connection: InventoryConnection) {
  // Inventory is an explicitly public, read-only feed. Never send the personal
  // session or a dealership staff credential to another origin.
  const res = await fetch(
    `${connection.api_base_url}/public/mysales/inventory`,
    { credentials: "omit", redirect: "error", cache: "no-store" },
  );
  const data = await res.json().catch(() => ({}));
  if (!res.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Inventory is unavailable. Your personal workspace is still available.",
    );
  return data as { items: RetailVehicle[]; as_of: string; limit: number };
}
