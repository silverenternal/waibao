"use client";

/**
 * T2901 — Single-button SSO provider tile.
 *
 * Renders one provider button. The visual design matches the rest of the
 * login page (gradient border, icon, hover translate). On click we
 * navigate the user to the IdP via the backend.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ShieldCheck,
  Shield,
  Building2,
  Globe,
  MessageCircle,
  Send,
  Users,
  ArrowRight,
  Loader2,
  type LucideIcon,
} from "lucide-react";
import {
  beginSSOLogin,
  type SSOProviderMeta,
  SSO_ICON_NAMES,
  SSO_COLOR_CLASSES,
} from "@/lib/auth-sso";

const ICON_MAP: Record<string, LucideIcon> = {
  ShieldCheck,
  Shield,
  Building2,
  Globe,
  MessageCircle,
  Send,
  Users,
};

export interface SSOButtonProps {
  provider: SSOProviderMeta;
  /** Where to send the user after a successful login. */
  relayState?: string;
  /** Disable the button while a parent is doing other work. */
  disabled?: boolean;
}

export function SSOButton({ provider, relayState, disabled }: SSOButtonProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const iconName = SSO_ICON_NAMES[provider.icon] ?? "Shield";
  const Icon = ICON_MAP[iconName] ?? Shield;
  const colorClass =
    SSO_COLOR_CLASSES[provider.color] ?? SSO_COLOR_CLASSES.default;

  const onClick = async () => {
    if (disabled || loading) return;
    setLoading(true);
    setError(null);
    try {
      const { url } = await beginSSOLogin(provider.slug, { relayState });
      window.location.href = url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "SSO login failed");
      setLoading(false);
    }
  };

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || loading}
      data-testid={`sso-button-${provider.slug}`}
      aria-label={`Continue with ${provider.display_name}`}
      className={`group relative w-full text-left rounded-xl border bg-[#151B2B]/60 backdrop-blur-sm p-5 transition-all duration-300 hover:translate-y-[-1px] hover:shadow-lg hover:shadow-black/20 disabled:opacity-50 disabled:cursor-not-allowed ${colorClass}`}
    >
      <div
        className={`absolute inset-0 rounded-xl bg-gradient-to-r ${colorClass} opacity-0 group-hover:opacity-100 transition-opacity duration-300`}
      />
      <div className="relative flex items-center gap-4">
        <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-white/5 border border-white/10 transition-colors">
          <Icon className="h-5 w-5" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-foreground">
              Continue with {provider.display_name}
            </span>
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground px-2 py-0.5 rounded-full border border-white/10 bg-white/5">
              {provider.protocol === "saml2" ? "SAML 2.0" : "OIDC"}
            </span>
          </div>
          <p className="text-sm text-muted-foreground mt-0.5">
            {error ?? provider.description}
          </p>
        </div>
        <div className="flex items-center">
          {loading ? (
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
          ) : (
            <ArrowRight className="h-5 w-5 text-muted-foreground group-hover:text-primary group-hover:translate-x-0.5 transition-all" />
          )}
        </div>
      </div>
    </button>
  );
}

export default SSOButton;
