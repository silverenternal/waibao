/**
 * T2901 — NextAuth.js SSO configuration.
 *
 * Vendor: NextAuth.js (Auth.js) — the de-facto SSO client for Next.js.
 *
 * The configuration is data-driven: we fetch the list of enabled IdPs
 * from the backend (`/api/auth/sso/providers`) and dynamically register
 * one NextAuth provider per backend IdP. This means adding a new IdP on
 * the backend automatically surfaces in the login UI without rebuilding
 * the frontend.
 *
 * The session is stored as a JWT in an HttpOnly cookie. The short-lived
 * access token (15 min) is refreshed automatically by `refreshSession()`
 * which is wired into the React provider.
 */
// NextAuth v5 (beta) uses the `NextAuthConfig` shape; the v4 type
// `NextAuthOptions` was removed. We import the closest equivalent so the
// rest of the module compiles without depending on internal beta APIs.
import type { NextAuthConfig } from "next-auth";

type NextAuthOptions = NextAuthConfig;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type SSOProviderSlug =
  | "okta"
  | "azure_ad"
  | "google"
  | "dingtalk"
  | "feishu"
  | "wecom";

export type SSOProviderCategory = "enterprise" | "cn";

export interface SSOProviderMeta {
  slug: SSOProviderSlug;
  display_name: string;
  category: SSOProviderCategory;
  protocol: "saml2" | "oidc";
  enabled: boolean;
  icon: string;
  color: string;
  description: string;
  scopes: string[];
}

export interface SSOSessionUser {
  id: string;
  email: string;
  name?: string;
  picture?: string;
  provider: SSOProviderSlug;
  role: string;
  organisation_id?: string | null;
  groups?: string[];
}

export interface SSOSessionResponse {
  user: {
    id: string;
    email: string;
    display_name?: string;
    given_name?: string;
    family_name?: string;
    picture?: string;
    role: string;
    is_active: boolean;
  };
  organisation?: {
    id: string;
    slug: string;
    name: string;
  } | null;
  access_token: string;
  access_token_expires_at: number;
  refresh_token: string;
  refresh_token_expires_at: number;
  session_id: string;
  provider: SSOProviderSlug;
  role: string;
  groups: string[];
  created: boolean;
  linked_by_email: boolean;
}

// ---------------------------------------------------------------------------
// Backend base URL
// ---------------------------------------------------------------------------

const BACKEND =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE) ||
  "http://localhost:8000";

// ---------------------------------------------------------------------------
// Public client API
// ---------------------------------------------------------------------------

/** Fetch the list of enabled SSO providers from the backend. */
export async function listSSOProviders(): Promise<SSOProviderMeta[]> {
  const res = await fetch(`${BACKEND}/api/auth/sso/providers`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(`Failed to list SSO providers: ${res.status}`);
  const body = await res.json();
  return body.providers ?? [];
}

/** Begin an SSO login flow — returns the IdP URL the browser should be sent to. */
export async function beginSSOLogin(
  slug: SSOProviderSlug,
  opts: { relayState?: string } = {}
): Promise<{ url: string; state: string }> {
  const qs = opts.relayState
    ? `?relay_state=${encodeURIComponent(opts.relayState)}`
    : "";
  const res = await fetch(
    `${BACKEND}/api/auth/sso/${slug}/login${qs}`,
    { credentials: "include" }
  );
  if (!res.ok) throw new Error(`Failed to start SSO flow: ${res.status}`);
  return res.json();
}

/** Exchange an OIDC `code` (or forward an `id_token`) at the callback endpoint. */
export async function completeSSOCallback(
  slug: SSOProviderSlug,
  payload: {
    code?: string;
    id_token?: string;
    SAMLResponse?: string;
    state?: string;
    nonce?: string;
    code_verifier?: string;
  }
): Promise<SSOSessionResponse> {
  const res = await fetch(`${BACKEND}/api/auth/sso/${slug}/callback`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch {}
    throw new Error(`SSO callback failed: ${detail}`);
  }
  return res.json();
}

/** Refresh the access token using the long-lived refresh token. */
export async function refreshSession(): Promise<SSOSessionResponse | null> {
  const res = await fetch(`${BACKEND}/api/auth/sso/refresh`, {
    method: "POST",
    credentials: "include",
  });
  if (res.status === 401) return null;
  if (!res.ok) throw new Error(`Refresh failed: ${res.status}`);
  const body = await res.json();
  return {
    user: {
      id: "",
      email: "",
      role: body.role ?? "member",
      is_active: true,
    },
    access_token: body.access_token,
    access_token_expires_at: body.access_token_expires_at,
    refresh_token: body.refresh_token,
    refresh_token_expires_at: body.refresh_token_expires_at,
    session_id: body.session_id,
    provider: "okta",
    role: "member",
    groups: [],
    created: false,
    linked_by_email: false,
  };
}

/** Sign the user out and clear the cookies. */
export async function signOutSSO(): Promise<void> {
  await fetch(`${BACKEND}/api/auth/sso/logout`, {
    method: "POST",
    credentials: "include",
  });
}

/** Return the current session info, or null if not logged in. */
export async function getCurrentSSOSession(): Promise<SSOSessionUser | null> {
  const res = await fetch(`${BACKEND}/api/auth/sso/me`, {
    credentials: "include",
    cache: "no-store",
  });
  if (res.status === 401) return null;
  if (!res.ok) throw new Error(`Failed to read session: ${res.status}`);
  const body = await res.json();
  return {
    id: body.user_id,
    email: body.email,
    provider: body.provider,
    role: body.role,
    organisation_id: body.organisation_id,
  };
}

// ---------------------------------------------------------------------------
// NextAuth options factory
// ---------------------------------------------------------------------------

/**
 * Build a `NextAuthOptions` object. We register one *Credentials* provider
 * per backend IdP — Credentials is the only NextAuth provider that lets us
 * post arbitrary JSON to a backend endpoint, which is exactly the
 * pattern we need for both SAML POST-binding and OIDC code-exchange.
 */
export function buildNextAuthOptions(
  providers: SSOProviderMeta[]
): NextAuthOptions {
  // Defer-import to avoid hard-failing when next-auth isn't installed in
  // the consumer environment. We still type the public surface as
  // NextAuthOptions.
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  let CredentialsProvider: any;
  try {
    // Lazy require so the module is optional at type-check time.
    CredentialsProvider = require("next-auth/providers/credentials").default;
  } catch {
    return { providers: [] } as unknown as NextAuthOptions;
  }

  return {
    session: { strategy: "jwt", maxAge: 30 * 24 * 60 * 60 },
    secret: process.env.NEXTAUTH_SECRET,
    pages: {
      signIn: "/login",
      error: "/login",
    },
    providers: providers
      .filter((p) => p.enabled)
      .map((p) =>
        CredentialsProvider({
          id: p.slug,
          name: p.display_name,
          credentials: {
            code: { label: "Code", type: "text" },
            id_token: { label: "ID Token", type: "text" },
            SAMLResponse: { label: "SAML Response", type: "text" },
            state: { label: "State", type: "text" },
            nonce: { label: "Nonce", type: "text" },
          },
          async authorize(credentials: Record<string, string> | undefined) {
            if (!credentials) return null;
            const payload: Record<string, string> = {};
            for (const k of ["code", "id_token", "SAMLResponse", "state", "nonce"]) {
              if (credentials[k]) payload[k] = credentials[k];
            }
            try {
              const session = await completeSSOCallback(p.slug, payload);
              return {
                id: session.user.id,
                email: session.user.email,
                name: session.user.display_name ?? session.user.email,
                image: session.user.picture,
                // Custom claims — NextAuth puts these on the JWT
                accessToken: session.access_token,
                refreshToken: session.refresh_token,
                provider: session.provider,
                role: session.role,
                organisationId: session.organisation?.id,
                groups: session.groups,
              } as any;
            } catch {
              return null;
            }
          },
        })
      ),
    callbacks: {
      async jwt({ token, user, account }: any) {
        if (user) {
          token.accessToken = user.accessToken;
          token.refreshToken = user.refreshToken;
          token.provider = user.provider;
          token.role = user.role;
          token.organisationId = user.organisationId;
          token.groups = user.groups;
        }
        // Auto-refresh: when the access token is about to expire, swap
        // it for a new one using the refresh token.
        if (
          token.refreshToken &&
          (!token.accessTokenExpiresAt ||
            Date.now() >= (token.accessTokenExpiresAt as number) - 30_000)
        ) {
          const refreshed = await refreshSession().catch(() => null);
          if (refreshed) {
            token.accessToken = refreshed.access_token;
            token.refreshToken = refreshed.refresh_token;
            token.accessTokenExpiresAt =
              refreshed.access_token_expires_at * 1000;
          }
        }
        return token;
      },
      async session({ session, token }: any) {
        session.user = {
          ...(session.user || {}),
          id: token.sub,
          role: token.role,
          provider: token.provider,
          organisationId: token.organisationId,
        };
        session.accessToken = token.accessToken;
        session.refreshToken = token.refreshToken;
        session.groups = token.groups;
        return session;
      },
    },
  };
}

// ---------------------------------------------------------------------------
// Icon mapping
// ---------------------------------------------------------------------------

/** Map a backend icon name to a lucide-react component (resolved lazily). */
export const SSO_ICON_NAMES: Record<string, string> = {
  "shield-check": "ShieldCheck",
  "shield": "Shield",
  "microsoft": "Building2",
  "google": "Globe",
  "message-circle": "MessageCircle",
  "send": "Send",
  "users": "Users",
};

// ---------------------------------------------------------------------------
// Per-provider default colour classes (Tailwind)
// ---------------------------------------------------------------------------

export const SSO_COLOR_CLASSES: Record<string, string> = {
  blue: "from-blue-500/20 to-cyan-500/20 border-blue-500/30 text-blue-400",
  indigo: "from-indigo-500/20 to-violet-500/20 border-indigo-500/30 text-indigo-400",
  red: "from-red-500/20 to-orange-500/20 border-red-500/30 text-red-400",
  cyan: "from-cyan-500/20 to-sky-500/20 border-cyan-500/30 text-cyan-400",
  green: "from-green-500/20 to-emerald-500/20 border-green-500/30 text-green-400",
  default: "from-white/5 to-white/5 border-white/10 text-foreground",
};
