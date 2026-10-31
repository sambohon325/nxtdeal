"use client";

import { BrandLogo } from "@/components/BrandLogo";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/api";
import { getSession, clearSession, authHeaders, saveSession } from "@/lib/auth";
import { BrandRibbon } from "@/components/BrandAngles";

// Shown after a forced first login (login()'s must_change_password flag — every
// admin-created or bulk-imported credential starts with a system-generated temp password,
// see BUILD_QUEUE.md Phase 9). Also reachable any time a signed-in user wants to change
// their own password — POST /auth/change-password needs the current password either way,
// it's not an admin reset.
export default function ChangePassword() {
  const router = useRouter();

  const [checkingSession, setCheckingSession] = useState(true);
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!getSession()) {
      router.push("/");
      return;
    }

    setCheckingSession(false);
  }, [router]);

  async function handleSubmit() {
    if (loading) return;

    if (!oldPassword || !newPassword || !confirmPassword) {
      setError("All fields are required.");
      return;
    }

    if (newPassword !== confirmPassword) {
      setError("New passwords don't match.");
      return;
    }

    setError("");
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}/auth/change-password`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({
          old_password: oldPassword,
          new_password: newPassword,
        }),
      });

      const data = await response.json();

      if (!response.ok || data.error) {
        if (data.error === "Invalid or expired token") {
          clearSession();
          router.push("/");
          return;
        }

        setError(data.error ?? "Unable to change password.");
        return;
      }

      const currentSession = getSession();
      if (currentSession && typeof data.token === "string") {
        saveSession({ ...currentSession, token: data.token });
      }

      router.push("/workspace");
    } catch {
      setError("Unable to reach NXTDeal backend.");
    } finally {
      setLoading(false);
    }
  }

  if (checkingSession) {
    return null;
  }

  return (
    <div className="h-screen overflow-hidden bg-[#111111] text-white flex flex-col">
      <header className="border-b border-zinc-900 px-8 py-4">
        <div className="flex items-center gap-3">
          <BrandLogo />
        </div>
      </header>

      <BrandRibbon />

      <main className="flex-1 overflow-y-auto flex items-center justify-center px-8">
        <div className="w-full max-w-md">
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-8">
            <h2 className="text-2xl font-medium mb-2">Set a New Password</h2>

            <p className="text-sm text-zinc-500 mb-6">
              Your account was created with a temporary password. Choose a new
              one to continue.
            </p>

            {error && (
              <div className="mb-4 text-sm text-red-400">{error}</div>
            )}

            <input
              type="password"
              placeholder="Temporary / current password"
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
              className="w-full h-12 px-4 mb-4 rounded-lg bg-zinc-950 border border-zinc-800 focus:outline-none"
            />

            <input
              type="password"
              placeholder="New password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full h-12 px-4 mb-4 rounded-lg bg-zinc-950 border border-zinc-800 focus:outline-none"
            />

            <input
              type="password"
              placeholder="Confirm new password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSubmit();
              }}
              className="w-full h-12 px-4 mb-6 rounded-lg bg-zinc-950 border border-zinc-800 focus:outline-none"
            />

            <button
              onClick={handleSubmit}
              disabled={loading}
              className="w-full h-12 rounded-lg brand-cta disabled:opacity-50 transition"
            >
              {loading ? "Updating..." : "Update Password"}
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
