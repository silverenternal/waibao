"use client";

import { useState } from "react";
import {
  installPlugin,
  createPurchase,
  formatPrice,
  type MarketplacePlugin,
} from "@/lib/api-marketplace";

interface InstallButtonProps {
  plugin: MarketplacePlugin;
  tenantId: string;
  userId?: string;
  defaultCurrency?: string;
}

export function InstallButton({
  plugin,
  tenantId,
  userId,
  defaultCurrency = "USD",
}: InstallButtonProps) {
  const [state, setState] = useState<
    "idle" | "installing" | "success" | "error"
  >("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [version, setVersion] = useState<string | null>(null);
  const isPaid = plugin.pricing_model !== "free";
  const [acceptTerms, setAcceptTerms] = useState(false);

  async function handleInstall() {
    setState("installing");
    setMessage(null);
    try {
      if (isPaid) {
        // 1) create the purchase
        const purchase = await createPurchase(plugin.slug, {
          plugin_id: plugin.id,
          tenant_id: tenantId,
          user_id: userId || tenantId,
          payment_method: "stripe",
          currency: defaultCurrency,
        });
        // In a real flow, redirect the user to Stripe Checkout here.
        // For this MVP we just record the purchase and call install.
        setMessage(
          `Purchase ${purchase.id} created — ${formatPrice(
            purchase.amount_cents, purchase.currency,
          )} (payment will be collected at checkout).`,
        );
      }
      // 2) call the install endpoint
      const result = await installPlugin(plugin.slug, {
        tenant_id: tenantId,
        waibao_version: "6.0.0",
        accept_terms: isPaid ? acceptTerms : true,
      });
      if (result.success) {
        setState("success");
        setVersion(result.version || null);
        setMessage(
          `Installed v${result.version} in ${Math.round(
            result.duration_ms,
          )}ms via ${result.detail?.via || "sdk"}.`,
        );
      } else {
        setState("error");
        setMessage(result.error || "Installation failed");
      }
    } catch (err) {
      setState("error");
      setMessage((err as Error).message || "Installation failed");
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-baseline justify-between">
        <div>
          <div className="text-2xl font-semibold text-slate-900">
            {formatPrice(plugin.price_cents)}
          </div>
          {isPaid && (
            <div className="text-xs uppercase text-slate-500">
              {plugin.pricing_model.replace("_", " ")}
            </div>
          )}
        </div>
        <div className="text-xs text-slate-500">
          {plugin.total_installs.toLocaleString()} installs
        </div>
      </div>
      {isPaid && (
        <label className="flex items-start gap-2 text-xs text-slate-600">
          <input
            type="checkbox"
            checked={acceptTerms}
            onChange={(e) => setAcceptTerms(e.target.checked)}
            className="mt-0.5"
            data-testid="accept-terms"
          />
          <span>
            I agree to pay {formatPrice(plugin.price_cents)} per
            {" "}{plugin.pricing_model.replace("_", " ")} and to the
            {" "}<a className="underline" href="/legal">terms of service</a>.
          </span>
        </label>
      )}
      <button
        type="button"
        onClick={handleInstall}
        disabled={state === "installing" || (isPaid && !acceptTerms)}
        className="w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
        data-testid="install-button"
      >
        {state === "installing"
          ? "Installing…"
          : isPaid
            ? "Buy & Install"
            : "1-click Install"}
      </button>
      {message && (
        <div
          className={
            state === "error"
              ? "rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700"
              : "rounded-md border border-green-200 bg-green-50 p-2 text-xs text-green-700"
          }
          data-testid="install-status"
        >
          {message}
        </div>
      )}
      {version && (
        <div className="text-xs text-slate-500">
          Installed version: <code className="font-mono">{version}</code>
        </div>
      )}
    </div>
  );
}
