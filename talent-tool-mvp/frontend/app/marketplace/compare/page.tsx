import { ErrorBoundary } from "@/components/ErrorBoundary";
import { generatePageMetadata } from "@/lib/metadata";
import { CompareClient } from "./_client";
import type { Metadata } from "next";

export const metadata: Metadata = generatePageMetadata({
  title: "HR 助手 — 简历并排比较 + 面试题模板",
  description:
    "HR 助手：选择 2-5 份简历并排比较（基本信息/技能/学历/经验/匹配度 + 差异高亮），一键导出 PDF/Word 比较报告；按岗位从题库生成 5-10 道面试题模板并导出。",
  path: "/marketplace/compare",
});

export default function ComparePage() {
  return (
    <ErrorBoundary>
      <CompareClient />
    </ErrorBoundary>
  );
}
