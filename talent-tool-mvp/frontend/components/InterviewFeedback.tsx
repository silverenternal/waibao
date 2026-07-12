"use client";

/**
 * InterviewFeedback — 面试总报告 (T1301).
 *
 * 组成:
 *   1. 总分 + 推荐等级 (4 档)
 *   2. 维度雷达 (基于 recharts)
 *   3. 整体 strengths / improvements
 *   4. summary 文案
 *
 * Props 兼容:
 *   - 直接传 report data 结构
 *   - 提供 dimensions / radar,任何字段缺失都用兜底
 */

import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

export interface DimensionScore {
  name: string;
  value: number;
  fullMark?: number;
}

export interface FeedbackReport {
  interview_id?: string;
  role?: string;
  overall_score?: number;
  recommendation?: string; // strong_yes | yes | consider | no
  summary?: string;
  radar?: Record<string, number>;
  dimension_scores?: Record<string, number>;
  strengths?: string[];
  improvements?: string[];
  total_questions?: number;
  answered_questions?: number;
  provider?: string;
}

const REC_LABEL: Record<string, { label: string; cls: string }> = {
  strong_yes: { label: "强烈推荐", cls: "bg-emerald-600 text-white" },
  yes: { label: "推荐", cls: "bg-sky-600 text-white" },
  consider: { label: "考虑", cls: "bg-amber-500 text-white" },
  no: { label: "暂缓", cls: "bg-slate-500 text-white" },
};

export function InterviewFeedback({
  report,
  className = "",
}: {
  report: FeedbackReport;
  className?: string;
}) {
  const radar: DimensionScore[] = Object.entries(report.radar || report.dimension_scores || {})
    .filter(([k]) => k !== "overall")
    .map(([name, value]) => ({
      name: prettyDim(name),
      value: Math.min(100, Math.max(0, Number(value) || 0)),
      fullMark: 100,
    }));

  const rec = REC_LABEL[report.recommendation || "consider"] || REC_LABEL.consider;

  return (
    <div className={`space-y-5 ${className}`} data-testid="interview-feedback">
      {/* 顶部 */}
      <div className="border rounded-2xl bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-500">整体表现</div>
            <div className="text-4xl font-bold text-slate-900 mt-1">
              {report.overall_score !== undefined ? Math.round(report.overall_score) : "—"}
              <span className="text-lg text-slate-400 ml-1">/ 100</span>
            </div>
            <div className="mt-2 text-xs text-slate-500">
              回答 {report.answered_questions ?? "—"} / {report.total_questions ?? "—"} 题
              {report.provider && report.provider !== "mock" && (
                <span className="ml-2 px-2 py-0.5 bg-emerald-50 text-emerald-700 rounded text-[10px]">
                  {report.provider} 提供
                </span>
              )}
              {report.provider === "mock" && (
                <span className="ml-2 px-2 py-0.5 bg-slate-100 text-slate-500 rounded text-[10px]">
                  mock 评估
                </span>
              )}
            </div>
          </div>
          <div className={`px-4 py-2 rounded-full text-sm font-semibold ${rec.cls}`} data-testid="rec-badge">
            {rec.label}
          </div>
        </div>

        {report.summary && (
          <p className="mt-4 text-sm text-slate-700 leading-relaxed whitespace-pre-wrap" data-testid="feedback-summary">
            {report.summary}
          </p>
        )}
      </div>

      {/* 雷达 */}
      {radar.length > 0 && (
        <div className="border rounded-2xl bg-white p-6 shadow-sm">
          <h3 className="text-base font-semibold text-slate-800 mb-3">维度雷达</h3>
          <div className="h-72 w-full" data-testid="radar-chart">
            <ResponsiveContainer>
              <RadarChart data={radar}>
                <PolarGrid strokeDasharray="3 3" />
                <PolarAngleAxis dataKey="name" tick={{ fontSize: 12 }} />
                <PolarRadiusAxis domain={[0, 100]} tick={{ fontSize: 10 }} />
                <Radar dataKey="value" stroke="#0ea5e9" fill="#0ea5e9" fillOpacity={0.35} />
                <Tooltip />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* 详细评分条 */}
      <div className="border rounded-2xl bg-white p-6 shadow-sm">
        <h3 className="text-base font-semibold text-slate-800 mb-3">维度详情</h3>
        <div className="space-y-3">
          {radar.map((d) => (
            <div key={d.name} className="flex items-center gap-3">
              <div className="w-24 text-sm text-slate-700">{d.name}</div>
              <div className="flex-1 h-2 bg-slate-100 rounded overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-sky-400 to-indigo-500"
                  style={{ width: `${d.value}%` }}
                />
              </div>
              <div className="w-12 text-right text-sm text-slate-700 tabular-nums">{Math.round(d.value)}</div>
            </div>
          ))}
          {radar.length === 0 && <div className="text-sm text-slate-400">暂无维度数据</div>}
        </div>
      </div>

      {/* strengths / improvements */}
      <div className="grid md:grid-cols-2 gap-4">
        <div className="border rounded-2xl bg-white p-6 shadow-sm">
          <h3 className="text-base font-semibold text-emerald-600 mb-3">亮点</h3>
          <ul className="space-y-2 text-sm text-slate-700">
            {(report.strengths || []).map((s, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-emerald-500">✓</span>
                <span>{s}</span>
              </li>
            ))}
            {(!report.strengths || report.strengths.length === 0) && (
              <li className="text-slate-400 text-sm">暂无</li>
            )}
          </ul>
        </div>
        <div className="border rounded-2xl bg-white p-6 shadow-sm">
          <h3 className="text-base font-semibold text-amber-600 mb-3">需要提升</h3>
          <ul className="space-y-2 text-sm text-slate-700">
            {(report.improvements || []).map((s, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-amber-500">→</span>
                <span>{s}</span>
              </li>
            ))}
            {(!report.improvements || report.improvements.length === 0) && (
              <li className="text-slate-400 text-sm">暂无</li>
            )}
          </ul>
        </div>
      </div>
    </div>
  );
}

function prettyDim(key: string) {
  const m: Record<string, string> = {
    communication: "沟通表达",
    depth: "深度",
    tradeoff: "取舍",
    creativity: "创新",
    ownership: "Owner 意识",
    security_awareness: "安全意识",
    metric_aware: "指标意识",
    calm: "冷静",
    planning: "规划",
    humility: "谦逊",
    empathy: "共情",
    judgment: "判断",
    architecture: "架构",
    metric: "度量",
  };
  return m[key] || key;
}

export default InterviewFeedback;
