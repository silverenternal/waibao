"use client";

/**
 * Refine authProvider — JWT-based using Supabase.
 *
 * Implements Refine's `AuthProvider` contract:
 *   - login   (email + password via supabase.auth.signInWithPassword)
 *   - logout  (supabase.auth.signOut)
 *   - check   (returns authenticated user, redirects to /login if missing)
 *   - getPermissions (returns role from app_metadata.role)
 *   - getIdentity (returns basic profile fields)
 *   - onError (logs auth errors for observability)
 *
 * Suited for hooking into @refinedev/core's `useLogin` / `useLogout` and
 * `<Authenticated>` gates.
 */

import type { AuthProvider } from "@refinedev/core";
import type { SupabaseClient } from "@supabase/supabase-js";

export const authProvider = (supabase: SupabaseClient): AuthProvider => ({
  login: async ({ email, password }) => {
    try {
      const { data, error } = await supabase.auth.signInWithPassword({
        email: String(email),
        password: String(password),
      });
      if (error) return { success: false, error: { name: "LoginError", message: error.message } };
      if (data?.session) {
        localStorage.setItem("refine-auth", JSON.stringify(data.session));
        return { success: true, redirectTo: "/admin" };
      }
      return { success: false, error: { name: "LoginError", message: "No session" } };
    } catch (e: any) {
      return { success: false, error: { name: "LoginError", message: e?.message ?? "Error" } };
    }
  },
  logout: async () => {
    localStorage.removeItem("refine-auth");
    await supabase.auth.signOut();
    return { success: true, redirectTo: "/login" };
  },
  check: async () => {
    const { data } = await supabase.auth.getSession();
    if (data.session) {
      return { authenticated: true };
    }
    return {
      authenticated: false,
      logout: true,
      redirectTo: "/login",
    };
  },
  getPermissions: async () => {
    const { data } = await supabase.auth.getUser();
    return (data.user?.app_metadata as any)?.role ?? "guest";
  },
  getIdentity: async () => {
    const { data } = await supabase.auth.getUser();
    if (!data.user) return null;
    return {
      id: data.user.id,
      name: (data.user.user_metadata as any)?.full_name ?? data.user.email,
      email: data.user.email ?? undefined,
      avatar: (data.user.user_metadata as any)?.avatar_url,
    };
  },
  onError: async (error) => {
    if (error?.statusCode === 401 || error?.statusCode === 403) {
      return { logout: true, redirectTo: "/login" };
    }
    return {};
  },
});

export default authProvider;
