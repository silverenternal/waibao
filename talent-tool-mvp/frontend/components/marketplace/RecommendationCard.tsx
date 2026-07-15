"use client";

/**
 * T6104 — Recommendation card.
 *
 * Renders one pushed talent↔role recommendation with the four match
 * sections the 甲方 contract asks for:
 *   1. 匹配分数 (0-100 progress bar)
 *   2. 匹配理由 (match_reasons)
 *   3. 能力缺口 (skill_gaps)
 *   4. 风险提示 (risks)
 *
 * When a detail (with resume_snapshot + contact_info) is supplied the card
 * also shows the full resume + contact. The 下载 button is admin-only
 * (gated by can_download / isAdmin).
 */
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  formatSalary,
  statusLabel,
  type RecommendationDetail,
  type RecommendationStatus,
  type RecommendationSummary,
} from "@/lib/api-recommendations";

const STATUS_BADGE: Record<
  RecommendationStatus,
  { variant: "secondary" | "outline" | "destructive"; className: string }
> = {
  pending: { variant: "secondary", className: "" },
  viewed: { variant: "outline", className: "text-sky-600" },
  accepted: { variant: "outline", className: "text-emerald-600" },
  rejected: { variant: "destructive", className: "" },
};

export interface RecommendationCardProps {
  recommendation: RecommendationSummary | RecommendationDetail;
  isAdmin?: boolean;
  busy?: boolean;
  onView?: (id: string) => void;
  onAccept?: (id: string) => void;
  onReject?: (id: string) => void;
  onDownload?: (id: string) => void;
}

function isDetail(
  r: RecommendationSummary | RecommendationDetail,
): r is RecommendationDetail {
  return (r as RecommendationDetail).resume_snapshot !== undefined;
}

export function RecommendationCard({
  recommendation: rec,
  isAdmin = false,
  busy = false,
  onView,
  onAccept,
  onReject,
  onDownload,
}: RecommendationCardProps) {
  const detail = isDetail(rec) ? rec : undefined;
  const canDownload = isAdmin || !!detail?.can_download;
  const status = STATUS_BADGE[rec.status];
  const snapshot = detail?.resume_snapshot;
  const contact = detail?.contact_info;

  return (
    <Card className="h-full transition hover:border-emerald-300 hover:shadow-md">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="flex flex-wrap items-center gap-2 text-base">
              <span className="truncate">
                {rec.candidate_name || "匿名候选人"}
              </span>
              <Badge variant={status.variant} className={status.className}>
                {statusLabel(rec.status)}
              </Badge>
            </CardTitle>
            <p className="mt-0.5 truncate text-sm text-slate-500">
              {rec.candidate_title || snapshot?.title || "人才"}
              {rec.role_title ? ` → ${rec.role_title}` : ""}
              {rec.company_name ? ` · ${rec.company_name}` : ""}
            </p>
          </div>
          <div className="shrink-0 text-right">
            <div className="text-lg font-semibold text-emerald-600">
              {rec.match_score}
              <span className="text-xs text-slate-400">/100</span>
            </div>
          </div>
        </div>

        {/* 匹配分数 progress */}
        <div className="mt-2">
          <Progress value={rec.match_score} aria-label="匹配分数" />
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {/* 匹配理由 */}
        <Section title="匹配理由" tone="emerald">
          {rec.match_reasons.length > 0 ? (
            <ul className="list-disc space-y-0.5 pl-4 text-sm text-slate-600">
              {rec.match_reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-400">综合画像相近</p>
          )}
        </Section>

        {/* 能力缺口 */}
        <Section title="能力缺口" tone="amber">
          {rec.skill_gaps.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {rec.skill_gaps.map((g, i) => (
                <Badge key={i} variant="outline" className="text-amber-600">
                  {g}
                </Badge>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-400">无明显缺口</p>
          )}
        </Section>

        {/* 风险提示 */}
        <Section title="风险提示" tone="rose">
          {rec.risks.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {rec.risks.map((r, i) => (
                <Badge key={i} variant="destructive">
                  {r}
                </Badge>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-400">无风险标记</p>
          )}
        </Section>

        {/* 完整简历 + 联系方式 (detail only) */}
        {snapshot && (
          <Section title="完整简历" tone="slate">
            <div className="space-y-1 text-sm text-slate-600">
              {snapshot.skills && snapshot.skills.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {snapshot.skills.slice(0, 8).map((s) => (
                    <Badge key={s} variant="secondary" className="font-normal">
                      {s}
                    </Badge>
                  ))}
                </div>
              )}
              <p className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-slate-500">
                {snapshot.city && <span>📍 {snapshot.city}</span>}
                {snapshot.seniority && <span>🎖 {snapshot.seniority}</span>}
                {snapshot.education && <span>🎓 {snapshot.education}</span>}
                {snapshot.experience_years != null && (
                  <span>⏳ {snapshot.experience_years}年</span>
                )}
                {snapshot.availability && (
                  <span className="text-emerald-600">● {snapshot.availability}</span>
                )}
              </p>
              <p className="text-xs text-slate-500">
                💰{" "}
                {formatSalary(snapshot.salary_min_k, snapshot.salary_max_k)}
              </p>
              {snapshot.summary && (
                <p className="text-xs leading-relaxed text-slate-500">
                  {snapshot.summary}
                </p>
              )}
            </div>

            {contact && (contact.email || contact.phone || contact.linkedin_url) && (
              <div className="mt-2 rounded-lg bg-slate-50 p-2 text-xs text-slate-600">
                <p className="font-medium text-slate-700">联系方式</p>
                {contact.email && <p>✉ {contact.email}</p>}
                {contact.phone && <p>📱 {contact.phone}</p>}
                {contact.linkedin_url && (
                  <p>
                    🔗{" "}
                    <a
                      href={contact.linkedin_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sky-600 hover:underline"
                    >
                      LinkedIn
                    </a>
                  </p>
                )}
              </div>
            )}
          </Section>
        )}

        {/* 操作 */}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          {onView && !detail && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => onView(rec.id)}
              disabled={busy}
            >
              查看详情
            </Button>
          )}
          {onAccept && rec.status !== "accepted" && rec.status !== "rejected" && (
            <Button
              size="sm"
              onClick={() => onAccept(rec.id)}
              disabled={busy}
            >
              接受
            </Button>
          )}
          {onReject && rec.status !== "accepted" && rec.status !== "rejected" && (
            <Button
              variant="destructive"
              size="sm"
              onClick={() => onReject(rec.id)}
              disabled={busy}
            >
              拒绝
            </Button>
          )}
          {onDownload && canDownload && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onDownload(rec.id)}
              disabled={busy}
              title={isAdmin ? "下载简历 (管理员)" : "下载简历"}
            >
              下载简历
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function Section({
  title,
  tone,
  children,
}: {
  title: string;
  tone: "emerald" | "amber" | "rose" | "slate";
  children: React.ReactNode;
}) {
  const toneClass: Record<typeof tone, string> = {
    emerald: "text-emerald-600",
    amber: "text-amber-600",
    rose: "text-rose-600",
    slate: "text-slate-700",
  };
  return (
    <div>
      <p className={`mb-1 text-xs font-medium ${toneClass[tone]}`}>{title}</p>
      {children}
    </div>
  );
}
