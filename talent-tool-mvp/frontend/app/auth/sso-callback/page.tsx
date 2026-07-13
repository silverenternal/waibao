"use client";

/**
 * T2901 — SSO callback page.
 *
 * The browser lands here after the IdP redirects back. We extract the
 * `code` / `id_token` / `SAMLResponse` from the URL and forward it to
 * the backend, which performs the actual exchange and mints a session.
 *
 * On success the backend sets the `at` / `rt` cookies and we redirect
 * the user to their destination page.
 *
 * Why a separate page? NextAuth's built-in callback page assumes the
 * provider's `signin` route — since we use the backend's own IdP SP
 * endpoint, we need a thin client wrapper to plumb the result.
 */

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { completeSSOCallback, type SSOProviderSlug } from "@/lib/auth-sso";
import { Loader2, AlertCircle, CheckCircle2 } from "lucide-react";

function SSOCallbackInner() {
  const router = useRouter();
  const search = useSearchParams();
  const [status, setStatus] = useState<"loading" | "success" | "error">(
    "loading"
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const provider = search.get("provider") as SSOProviderSlug | null;
    if (!provider) {
      setStatus("error");
      setError("Missing `provider` query parameter");
      return;
    }
    const payload: Record<string, string> = {};
    for (const k of [
      "code",
      "id_token",
      "SAMLResponse",
      "state",
      "nonce",
      "RelayState",
    ]) {
      const v = search.get(k) ?? search.get(k.toLowerCase());
      if (v) payload[k === "RelayState" ? "RelayState" : k] = v;
    }
    // OIDC: if the IdP only posted back `code` we still need PKCE
    // verifier from sessionStorage (set when we redirected away).
    const codeVerifier =
      typeof window !== "undefined"
        ? window.sessionStorage.getItem(`pkce_verifier_${provider}`)
        : null;
    if (codeVerifier) payload.code_verifier = codeVerifier;

    let cancelled = false;
    (async () => {
      try {
        const session = await completeSSOCallback(provider, payload);
        if (cancelled) return;
        // Persist the access token for the rest of the SPA to use.
        try {
          window.sessionStorage.setItem(
            "sso_access_token",
            session.access_token
          );
          window.sessionStorage.setItem(
            "sso_session",
            JSON.stringify(session)
          );
        } catch {}
        setStatus("success");
        const dest =
          search.get("relay_state") ||
          search.get("RelayState") ||
          "/mothership/dashboard";
        // Small delay so the success UI is perceptible.
        setTimeout(() => router.push(dest), 500);
      } catch (err) {
        if (cancelled) return;
        setStatus("error");
        setError(err instanceof Error ? err.message : "SSO callback failed");
      }
    })();
    return () => { cancelled = true; };
  }, [router, search]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-mesh bg-grid text-foreground">
      <div className="rounded-2xl border border-white/10 bg-[#151B2B]/80 backdrop-blur-sm p-8 max-w-md w-full text-center space-y-4">
        {status === "loading" && (
          <>
            <Loader2 className="h-10 w-10 text-primary animate-spin mx-auto" />
            <h1 className="text-xl font-semibold">Completing sign-in…</h1>
            <p className="text-sm text-muted-foreground">
              Verifying your identity and provisioning your account.
            </p>
          </>
        )}
        {status === "success" && (
          <>
            <CheckCircle2 className="h-10 w-10 text-emerald-400 mx-auto" />
            <h1 className="text-xl font-semibold">Signed in</h1>
            <p className="text-sm text-muted-foreground">
              Redirecting you to the dashboard…
            </p>
          </>
        )}
        {status === "error" && (
          <>
            <AlertCircle className="h-10 w-10 text-red-400 mx-auto" />
            <h1 className="text-xl font-semibold">Sign-in failed</h1>
            <p className="text-sm text-red-300">{error}</p>
            <button
              type="button"
              onClick={() => router.push("/login")}
              className="inline-flex items-center justify-center rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-sm hover:bg-white/10"
            >
              Back to sign-in
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default function SSOCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center">
          <Loader2 className="h-8 w-8 text-primary animate-spin" />
        </div>
      }
    >
      <SSOCallbackInner />
    </Suspense>
  );
}
