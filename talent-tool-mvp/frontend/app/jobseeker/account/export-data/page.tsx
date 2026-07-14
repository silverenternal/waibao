"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * 求职者 — 数据导出 (GDPR 数据可携权).
 */

import * as React from "react";
import { useLocale } from "next-intl";
import { Download, FileJson, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function ExportDataPage() {
  const locale = useLocale();
  const lang = locale.toLowerCase().startsWith("zh")
    ? "zh"
    : locale.toLowerCase().startsWith("ja")
      ? "ja"
      : "en";

  const [loading, setLoading] = React.useState(false);
  const [downloadedAt, setDownloadedAt] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const exportData = async (format: "json" | "csv") => {
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem("sb_token") || "";
      const res = await fetch(`/api/gdpr/export?format=${format}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `waibao-export-${Date.now()}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
      setDownloadedAt(new Date().toISOString());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <ErrorBoundary>(<div className="mx-auto max-w-2xl space-y-6 px-4 py-8 sm:px-6">
        <header>
          <h1 className="text-2xl font-bold tracking-tight">
            {lang === "zh" ? "导出我的数据" : lang === "ja" ? "データエクスポート" : "Export my data"}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {lang === "zh"
              ? "您有权随时获取本平台存储的全部与您有关的个人数据副本。"
              : lang === "ja"
                ? "プラットフォームに保存されているあなたの個人データのコピーを取得できます。"
                : "You have the right to obtain a copy of all personal data we hold about you."}
          </p>
        </header>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {lang === "zh" ? "导出格式" : lang === "ja" ? "形式" : "Export format"}
            </CardTitle>
            <CardDescription>
              {lang === "zh"
                ? "JSON 适合二次处理,CSV 适合用 Excel 打开。"
                : lang === "ja"
                  ? "JSON は処理向け、CSV は Excel で閲覧できます。"
                  : "JSON is good for further processing; CSV works in Excel."}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-3">
            <Button onClick={() => exportData("json")} disabled={loading}>
              {loading ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <FileJson className="size-4" />
              )}
              {lang === "zh" ? "导出 JSON" : lang === "ja" ? "JSON 出力" : "Export JSON"}
            </Button>
            <Button onClick={() => exportData("csv")} variant="outline" disabled={loading}>
              <Download className="size-4" />
              {lang === "zh" ? "导出 CSV" : lang === "ja" ? "CSV 出力" : "Export CSV"}
            </Button>
          </CardContent>
        </Card>
        {downloadedAt && (
          <div className="rounded-lg border border-emerald-300/40 bg-emerald-50/50 p-4 text-sm text-emerald-700">
            {lang === "zh"
              ? "导出已开始,文件应在几秒钟内下载完成。"
              : lang === "ja"
                ? "ダウンロードが始まりました。すぐにファイルがダウンロードされます。"
                : "Export started; file should download shortly."}
          </div>
        )}
        {error && (
          <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        )}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">
              {lang === "zh" ? "包含的字段" : lang === "ja" ? "含まれるデータ" : "What's included"}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs leading-relaxed text-muted-foreground">
            <ul className="ml-4 list-disc space-y-1">
              <li>{lang === "zh" ? "账户基础信息(姓名 / 邮箱 / 手机)" : "Account info (name / email / phone)"}</li>
              <li>{lang === "zh" ? "简历与候选人档案" : "Resume & candidate profile"}</li>
              <li>{lang === "zh" ? "协作房间与对话记录" : "Collaboration rooms & chat"}</li>
              <li>{lang === "zh" ? "同意与隐私偏好历史" : "Consent & privacy preferences"}</li>
              <li>{lang === "zh" ? "审计日志(脱敏)" : "Audit logs (anonymized)"}</li>
            </ul>
          </CardContent>
        </Card>
      </div>)</ErrorBoundary>
  );
}