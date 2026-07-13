"use client";

/**
 * Admin / Whitelabel (v7.0 T3003)
 *
 * Lets a tenant admin configure their white-label branding:
 *   - product name, domain, support email, locale
 *   - logo URL, favicon URL
 *   - primary / secondary / accent colours
 *   - font family, footer text, hide-powered-by flag
 *   - custom CSS override
 *
 * All writes go through PUT /api/whitelabel/{tenant_id}; CSS variables
 * are pushed into :root immediately so a preview pane reflects the
 * change without a refresh.
 */

import * as React from "react";

import { useWhiteLabel } from "@/components/WhiteLabelProvider";
import { whitelabelApi, type Branding } from "@/lib/theme";

const FONT_FAMILIES = [
  "Inter",
  "Roboto",
  "Helvetica",
  "Arial",
  "PingFang SC",
  "Microsoft YaHei",
  "Source Han Sans SC",
  "Noto Sans CJK SC",
  "Hiragino Sans",
  "Yu Gothic",
  "system-ui",
];

const LOCALE_OPTIONS = ["zh-CN", "en-US", "ja-JP"];

interface FieldProps {
  label: string;
  hint?: string;
  children: React.ReactNode;
}

function Field({ label, hint, children }: FieldProps) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium text-foreground">{label}</span>
      {children}
      {hint ? <span className="text-xs text-muted-foreground">{hint}</span> : null}
    </label>
  );
}

export default function AdminWhitelabelPage() {
  const { tenantId, branding, refresh, update } = useWhiteLabel();
  const [form, setForm] = React.useState<Branding>(branding);
  const [busy, setBusy] = React.useState(false);
  const [msg, setMsg] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    setForm(branding);
  }, [branding]);

  const onChange = <K extends keyof Branding>(k: K, v: Branding[K]) => {
    setForm((prev) => ({ ...prev, [k]: v }));
  };

  const onSave = async () => {
    setBusy(true);
    setMsg(null);
    setError(null);
    try {
      await update(form);
      await refresh();
      setMsg("保存成功");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const onReset = async () => {
    setBusy(true);
    try {
      await whitelabelApi.remove(tenantId);
      await refresh();
      setMsg("已重置为默认品牌");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">白标 / Whitelabel</h1>
        <p className="text-sm text-muted-foreground">
          租户 ID: <code className="rounded bg-muted px-1">{tenantId}</code> —
          客户可在此配置 Logo、域名、品牌色、字体、邮件模板与 PDF 报告水印。
        </p>
      </header>

      <section className="grid gap-6 md:grid-cols-2">
        <Field label="产品名" hint="对外显示的产品名称 (2-64 字符)">
          <input
            className="rounded border px-3 py-2"
            value={form.product_name}
            onChange={(e) => onChange("product_name", e.target.value)}
          />
        </Field>
        <Field label="域名" hint="客户的私有化部署域名 (例: hire.acme.com)">
          <input
            className="rounded border px-3 py-2"
            value={form.domain}
            placeholder="hire.example.com"
            onChange={(e) => onChange("domain", e.target.value)}
          />
        </Field>
        <Field label="Logo URL" hint="https URL,建议 PNG/SVG 透明底">
          <input
            className="rounded border px-3 py-2"
            value={form.logo_url}
            placeholder="https://cdn.example.com/logo.png"
            onChange={(e) => onChange("logo_url", e.target.value)}
          />
        </Field>
        <Field label="Favicon URL">
          <input
            className="rounded border px-3 py-2"
            value={form.favicon_url}
            placeholder="https://cdn.example.com/favicon.ico"
            onChange={(e) => onChange("favicon_url", e.target.value)}
          />
        </Field>
        <Field label="主色 Primary">
          <div className="flex items-center gap-3">
            <input
              type="color"
              value={form.primary_color}
              onChange={(e) => onChange("primary_color", e.target.value)}
              className="h-10 w-14 cursor-pointer rounded border"
            />
            <input
              className="flex-1 rounded border px-3 py-2"
              value={form.primary_color}
              onChange={(e) => onChange("primary_color", e.target.value)}
            />
          </div>
        </Field>
        <Field label="次色 Secondary">
          <div className="flex items-center gap-3">
            <input
              type="color"
              value={form.secondary_color}
              onChange={(e) => onChange("secondary_color", e.target.value)}
              className="h-10 w-14 cursor-pointer rounded border"
            />
            <input
              className="flex-1 rounded border px-3 py-2"
              value={form.secondary_color}
              onChange={(e) => onChange("secondary_color", e.target.value)}
            />
          </div>
        </Field>
        <Field label="强调色 Accent">
          <div className="flex items-center gap-3">
            <input
              type="color"
              value={form.accent_color}
              onChange={(e) => onChange("accent_color", e.target.value)}
              className="h-10 w-14 cursor-pointer rounded border"
            />
            <input
              className="flex-1 rounded border px-3 py-2"
              value={form.accent_color}
              onChange={(e) => onChange("accent_color", e.target.value)}
            />
          </div>
        </Field>
        <Field label="字体">
          <select
            className="rounded border px-3 py-2"
            value={form.font_family}
            onChange={(e) => onChange("font_family", e.target.value)}
          >
            {FONT_FAMILIES.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </Field>
        <Field label="客服邮箱">
          <input
            className="rounded border px-3 py-2"
            value={form.support_email}
            onChange={(e) => onChange("support_email", e.target.value)}
          />
        </Field>
        <Field label="页脚文本" hint="出现在邮件 + PDF 末尾">
          <input
            className="rounded border px-3 py-2"
            value={form.footer_text}
            onChange={(e) => onChange("footer_text", e.target.value)}
          />
        </Field>
        <Field label="默认语言">
          <select
            className="rounded border px-3 py-2"
            value={form.locale}
            onChange={(e) =>
              onChange("locale", e.target.value as Branding["locale"])
            }
          >
            {LOCALE_OPTIONS.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </Field>
        <Field label="隐藏 Powered by" hint="私有化部署客户常见诉求">
          <input
            type="checkbox"
            checked={form.hide_powered_by}
            onChange={(e) => onChange("hide_powered_by", e.target.checked)}
          />
        </Field>
        <Field label="自定义 CSS" hint="最多 8192 字符,直接注入 :root">
          <textarea
            className="rounded border px-3 py-2 font-mono text-xs"
            rows={5}
            value={form.custom_css}
            onChange={(e) => onChange("custom_css", e.target.value)}
          />
        </Field>
      </section>

      <section className="flex flex-wrap items-center gap-3">
        <button
          onClick={onSave}
          disabled={busy}
          className="rounded bg-primary px-4 py-2 text-white disabled:opacity-50"
          style={{ backgroundColor: "var(--color-primary)" }}
        >
          {busy ? "保存中..." : "保存"}
        </button>
        <button
          onClick={onReset}
          disabled={busy}
          className="rounded border px-4 py-2 text-sm"
        >
          重置为默认
        </button>
        {msg ? <span className="text-sm text-emerald-600">{msg}</span> : null}
        {error ? <span className="text-sm text-rose-600">{error}</span> : null}
      </section>

      <section
        className="rounded-xl border p-6"
        style={{
          background: "var(--color-secondary)",
          color: "white",
          fontFamily: "var(--font-family)",
        }}
      >
        <h2 className="text-xl font-semibold" style={{ color: "var(--color-primary)" }}>
          {form.product_name}
        </h2>
        <p style={{ color: "var(--color-accent)" }}>实时预览 — 当前 CSS 变量已应用。</p>
        <p className="mt-4 text-xs opacity-70">{form.footer_text}</p>
      </section>
    </div>
  );
}