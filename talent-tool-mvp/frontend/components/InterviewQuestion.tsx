"use client";

/**
 * InterviewQuestion — 单题展示 + 评分回显 (T1301).
 *
 * 用在面试进行中和结束后回顾:
 *   - 题干 + 期望要点
 *   - 候选人回答 transcript / 视频
 *   - 评分 badge + 维度 radar
 */

export interface QuestionData {
  id: string;
  seq: number;
  category: string;
  title: string;
  prompt: string;
  expected_points?: string[];
  difficulty?: string;
  qtype?: string;
  skills?: string[];
}

export interface AnswerResultData {
  overall?: number;
  band?: string;
  dimensions?: Record<string, number>;
  strengths?: string[];
  improvements?: string[];
  feedback?: string;
  transcript?: string;
}

const BAND_COLOR: Record<string, string> = {
  weak: "bg-rose-100 text-rose-700",
  fair: "bg-amber-100 text-amber-700",
  good: "bg-sky-100 text-sky-700",
  excellent: "bg-emerald-100 text-emerald-700",
};

const BAND_LABEL: Record<string, string> = {
  weak: "薄弱",
  fair: "尚可",
  good: "良好",
  excellent: "优秀",
};

export function InterviewQuestion({
  question,
  answer,
  showVideoUrl,
}: {
  question: QuestionData;
  answer?: AnswerResultData;
  showVideoUrl?: string;
}) {
  const band = answer?.band ?? "fair";
  const overall = answer?.overall;
  return (
    <div
      className="border rounded-xl bg-white p-5 space-y-3 shadow-sm"
      data-testid={`interview-q-${question.seq}`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-slate-400">Q{question.seq}</span>
          <span className="text-xs px-2 py-0.5 bg-slate-100 rounded text-slate-600">
            {question.qtype || "behavioral"}
          </span>
          <span className="text-xs px-2 py-0.5 bg-slate-100 rounded text-slate-600">
            {question.difficulty || "mid"}
          </span>
        </div>
        {overall !== undefined && (
          <span
            className={`text-sm font-semibold px-2 py-1 rounded ${BAND_COLOR[band] || BAND_COLOR.fair}`}
            data-testid="question-band"
          >
            {Math.round(overall)} 分 · {BAND_LABEL[band] || band}
          </span>
        )}
      </div>

      <div>
        <h3 className="text-base font-semibold text-slate-800 mb-1">{question.title}</h3>
        <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">{question.prompt}</p>
      </div>

      {question.skills && question.skills.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {question.skills.map((s) => (
            <span key={s} className="text-xs px-2 py-0.5 rounded bg-indigo-50 text-indigo-600">
              #{s}
            </span>
          ))}
        </div>
      )}

      {answer?.transcript && (
        <details className="border-t pt-3 mt-3">
          <summary className="text-xs text-slate-500 cursor-pointer">查看候选人回答文本</summary>
          <p className="mt-2 text-sm text-slate-700 whitespace-pre-wrap">{answer.transcript}</p>
        </details>
      )}

      {showVideoUrl && (
        <div className="text-xs text-slate-500 break-all">
          视频:{" "}
          <a className="text-sky-600 hover:underline" href={showVideoUrl} target="_blank" rel="noreferrer">
            {showVideoUrl}
          </a>
        </div>
      )}

      {answer && (
        <div className="grid md:grid-cols-2 gap-3 pt-3 border-t border-slate-100">
          <div>
            <div className="text-xs font-semibold text-slate-500 mb-1">亮点</div>
            <ul className="space-y-1 text-sm text-slate-700">
              {(answer.strengths || []).map((s, i) => (
                <li key={i}>+ {s}</li>
              ))}
              {(!answer.strengths || answer.strengths.length === 0) && (
                <li className="text-slate-400">—</li>
              )}
            </ul>
          </div>
          <div>
            <div className="text-xs font-semibold text-slate-500 mb-1">改进建议</div>
            <ul className="space-y-1 text-sm text-slate-700">
              {(answer.improvements || []).map((s, i) => (
                <li key={i}>→ {s}</li>
              ))}
              {(!answer.improvements || answer.improvements.length === 0) && (
                <li className="text-slate-400">—</li>
              )}
            </ul>
          </div>
          {answer.feedback && (
            <div className="md:col-span-2 bg-slate-50 rounded-md px-3 py-2 text-sm text-slate-700">
              {answer.feedback}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default InterviewQuestion;
