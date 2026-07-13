"use client";

/**
 * /jobseeker/interview-prep/[role_id] — v9.1 角色准备练习
 *
 * 不依赖后端 API 的"轻量级"练习场:
 *   - 10 道角色高频题(行为 + 技术 + 反问)
 *   - 每题支持"文字"或"语音"回答(VoiceRecorder → /api/voice/transcribe)
 *   - 完成后由前端规则引擎给出 5 维评分 + 反馈报告
 *   - 可重新练习、导出建议
 *
 * 设计目标:让候选人在没有正式 AI 面试官的情况下也能完成一轮结构化自测。
 */

import { forwardRef, use, useImperativeHandle, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";

const VoiceRecorder = dynamic(() => import("@/components/VoiceRecorder"), {
  ssr: false,
  loading: () => (
    <div className="border rounded-lg p-4 bg-slate-50 text-sm text-slate-400">
      加载录音组件中…
    </div>
  ),
});

type QuestionKind = "behavioral" | "technical" | "reverse_q" | "self_intro";

interface PrepQuestion {
  id: string;
  kind: QuestionKind;
  kind_label: string;
  title: string;
  prompt: string;
  hints: string[];
  keywords: string[];
  expected_seconds: number;
}

interface AnswerEntry {
  question_id: string;
  text: string;
  provider?: string;
  char_count: number;
  word_count: number;
  submitted_at: string;
  score: number;
  band: "weak" | "fair" | "good" | "excellent";
  feedback: string;
  hits: string[];
  misses: string[];
}

interface PrepReport {
  role: string;
  role_label: string;
  generated_at: string;
  total_questions: number;
  answered: number;
  overall: number;
  band: "weak" | "fair" | "good" | "excellent";
  radar: {
    content: number;
    structure: number;
    depth: number;
    fluency: number;
    relevance: number;
  };
  summary: string;
  strengths: string[];
  improvements: string[];
  per_question: AnswerEntry[];
}

const ROLE_META: Record<string, { label: string; icon: string; summary: string }> = {
  backend_engineer: {
    label: "后端工程师",
    icon: "🛠",
    summary: "考察系统设计、并发与数据库、API 工程化、故障排查。",
  },
  frontend_engineer: {
    label: "前端工程师",
    icon: "🎨",
    summary: "考察组件化、性能优化、可访问性、跨端兼容。",
  },
  fullstack_engineer: {
    label: "全栈工程师",
    icon: "🧱",
    summary: "考察前后端协同、全链路设计与部署、数据库建模。",
  },
  mobile_engineer: {
    label: "移动端工程师",
    icon: "📱",
    summary: "考察原生 / 跨端、离线与同步、性能与电量。",
  },
  data_engineer: {
    label: "数据工程师",
    icon: "🗄",
    summary: "考察数仓建模、ETL 流水线、数据治理。",
  },
  data_scientist: {
    label: "数据科学家",
    icon: "📊",
    summary: "考察实验设计、统计推断、业务问题建模。",
  },
  product_manager: {
    label: "产品经理",
    icon: "🧭",
    summary: "考察需求分析、用户洞察、跨团队协作。",
  },
  designer: {
    label: "设计师",
    icon: "✏️",
    summary: "考察问题定义、方案演绎、可用性测试。",
  },
  marketing: {
    label: "市场",
    icon: "📣",
    summary: "考察市场策略、用户增长、品牌叙事。",
  },
  sales: {
    label: "销售",
    icon: "🤝",
    summary: "考察客户开发、谈判技巧、长期关系。",
  },
};

const KEYWORD_BANK: Record<string, string[]> = {
  backend_engineer: [
    "高并发", "微服务", "数据库", "索引", "缓存", "消息队列", "监控", "可观测性",
    "事务", "锁", "幂等", "重试", "降级", "限流", "熔断", "分库分表", "读写分离",
    "CI/CD", "容器化", "Kubernetes", "接口", "REST", "GraphQL", "gRPC",
  ],
  frontend_engineer: [
    "组件化", "虚拟 DOM", "Diff", "Fiber", "状态管理", "性能", "懒加载",
    "可访问性", "A11y", "WCAG", "SEO", "SSR", "CSR", "SSG", "ISR",
    "TypeScript", "测试", "E2E", "跨端", "响应式", "动画", "布局", "浏览器渲染",
  ],
  fullstack_engineer: [
    "全链路", "API 设计", "鉴权", "RBAC", "DevOps", "可观测性", "日志",
    "架构", "事务", "缓存", "CDN", "数据库建模", "PostgreSQL", "MySQL", "Redis",
    "Kafka", "对象存储", "S3", "云原生",
  ],
  mobile_engineer: [
    "原生", "跨端", "离线", "同步", "电量", "启动时间", "包大小", "内存",
    "线程模型", "协程", "渲染", "动画", "Crash", "ANR", "App Bundle",
    "推送", "热更新", "RN", "Flutter", "Swift", "Kotlin", "Compose",
  ],
  data_engineer: [
    "数仓", "分层", "ETL", "ELT", "Airflow", "Spark", "Flink", "Kafka",
    "分区", "分桶", "ORC", "Parquet", "Iceberg", "数据治理", "血缘", "SLA",
    "SCD", "数据质量", "调度",
  ],
  data_scientist: [
    "实验", "A/B", "显著性", "假设检验", "因果", "贝叶斯", "回归", "分类",
    "指标", "北极星", "漏斗", "留存", "归因", "增量", "DR", "样本量",
    "偏差", "选择偏差", "幸存者偏差",
  ],
  product_manager: [
    "用户访谈", "需求分层", "MVP", "PRD", "路线图", "OKR", "北极星",
    "增长", "留存", "商业化", "定价", "数据驱动", "A/B 实验",
    "跨团队", "Stakeholder", "用户故事", "验收标准",
  ],
  designer: [
    "用户研究", "可用性测试", "信息架构", "交互", "视觉", "Design System",
    "组件库", "可访问性", "WCAG", "Figma", "Auto Layout", "原型",
    "用户旅程", "Job Story", "动效", "设计评审", "设计走查",
  ],
  marketing: [
    "品牌", "增长", "漏斗", "留存", "获客成本", "CAC", "LTV", "ROI",
    "内容", "私域", "社群", "SEO", "SEM", "社交媒体", "PR", "KOL",
    "活动", "发布会",
  ],
  sales: [
    "客户开发", "ICP", "价值主张", "痛点", "决策链", "异议处理", "谈判",
    "报价", "复购", "续约", "客户成功", "CRM", "Salesforce", "HubSpot",
    "业绩", "Pipeline",
  ],
};

const KIND_LABEL: Record<QuestionKind, string> = {
  behavioral: "行为面试",
  technical: "技术深度",
  reverse_q: "反问环节",
  self_intro: "自我介绍",
};

function buildQuestions(roleId: string): PrepQuestion[] {
  const kw = KEYWORD_BANK[roleId] || [];
  const pick = (i: number, n = 4) => kw.slice(i, i + n);
  return [
    {
      id: "q01",
      kind: "self_intro",
      kind_label: KIND_LABEL.self_intro,
      title: "1 分钟自我介绍",
      prompt: "请用 60 秒内介绍你自己:背景 + 核心能力 + 与本岗位最相关的 2 段经历。",
      hints: ["控制时间在 60 秒左右", "结尾抛一个亮点让面试官追问"],
      keywords: [...pick(0, 3), "项目", "业绩"],
      expected_seconds: 60,
    },
    {
      id: "q02",
      kind: "behavioral",
      kind_label: KIND_LABEL.behavioral,
      title: "最具挑战的项目",
      prompt: "讲一个你主导过的、最具挑战的项目,目标是?过程中你做了什么?结果如何?",
      hints: ["推荐 STAR 法则:情景/任务/行动/结果", "突出你个人的决策点"],
      keywords: [...pick(3, 4), "挑战", "复盘"],
      expected_seconds: 180,
    },
    {
      id: "q03",
      kind: "behavioral",
      kind_label: KIND_LABEL.behavioral,
      title: "团队冲突如何处理",
      prompt: "你和同事在方案上产生严重分歧,你会怎么处理?请举一个具体例子。",
      hints: ["先描述冲突背景,再说你的处理", "强调沟通与共识"],
      keywords: ["沟通", "共识", "决策", "团队", "数据", "复盘"],
      expected_seconds: 150,
    },
    {
      id: "q04",
      kind: "technical",
      kind_label: KIND_LABEL.technical,
      title: `核心技能 · ${kw[0] || "技术深度"}`,
      prompt: `请深入讲讲你在 "${kw[0] || "核心技术"}" 方面的实战经验,以及踩过的坑。`,
      hints: ["结合真实项目", "说出具体数据/数字"],
      keywords: [...pick(0, 5)],
      expected_seconds: 180,
    },
    {
      id: "q05",
      kind: "technical",
      kind_label: KIND_LABEL.technical,
      title: `系统设计 · ${kw[1] || "架构"}`,
      prompt: `如果让你从 0 设计一个 "${kw[1] || "核心系统"}" 场景,你会如何拆解?关键模块是什么?`,
      hints: ["先说需求边界", "再拆模块/接口", "最后说演进方向"],
      keywords: [...pick(2, 5), "架构", "模块"],
      expected_seconds: 240,
    },
    {
      id: "q06",
      kind: "technical",
      kind_label: KIND_LABEL.technical,
      title: `故障与排查 · ${kw[2] || "监控"}`,
      prompt: `请讲一次你参与的线上故障,根因是什么?你做了什么止血和根治动作?`,
      hints: ["时间线 + 关键决策", "可观测性 / 监控点"],
      keywords: [...pick(4, 4), "监控", "复盘", "告警"],
      expected_seconds: 150,
    },
    {
      id: "q07",
      kind: "behavioral",
      kind_label: KIND_LABEL.behavioral,
      title: "成长与反思",
      prompt: "过去 1 年你做过的最重要的一个学习/提升是什么?为什么?",
      hints: ["诚实 + 行动 + 验证", "避免空话"],
      keywords: ["学习", "成长", "反思", "输入", "输出"],
      expected_seconds: 120,
    },
    {
      id: "q08",
      kind: "behavioral",
      kind_label: KIND_LABEL.behavioral,
      title: "为什么是我们",
      prompt: `为什么想加入我们公司 / 这个岗位?你希望获得什么?`,
      hints: ["具体到业务、团队、技术栈", "避免「贵公司很大」这种空话"],
      keywords: ["业务", "团队", "成长", "价值", "匹配"],
      expected_seconds: 90,
    },
    {
      id: "q09",
      kind: "reverse_q",
      kind_label: KIND_LABEL.reverse_q,
      title: "反问 · 团队",
      prompt: "请向面试官提一个关于团队协作 / 工程文化的问题。",
      hints: ["显示你已经做了功课", "避免问薪资福利(留给 HR)"],
      keywords: ["团队", "协作", "工程文化", "流程", "代码评审"],
      expected_seconds: 60,
    },
    {
      id: "q10",
      kind: "reverse_q",
      kind_label: KIND_LABEL.reverse_q,
      title: "反问 · 业务",
      prompt: "请向面试官提一个关于业务方向 / 产品演进的问题。",
      hints: ["结合行业趋势", "展示长期思考"],
      keywords: ["业务", "方向", "演进", "竞争", "机会"],
      expected_seconds: 60,
    },
  ];
}

const BAND_COLOR: Record<AnswerEntry["band"], string> = {
  weak: "bg-rose-100 text-rose-700",
  fair: "bg-amber-100 text-amber-700",
  good: "bg-sky-100 text-sky-700",
  excellent: "bg-emerald-100 text-emerald-700",
};

const BAND_LABEL: Record<AnswerEntry["band"], string> = {
  weak: "待加强",
  fair: "一般",
  good: "良好",
  excellent: "优秀",
};

function evaluate(text: string, keywords: string[]): Omit<AnswerEntry, "question_id" | "text" | "provider" | "char_count" | "word_count" | "submitted_at"> {
  const trimmed = text.trim();
  const length = trimmed.length;
  const sentences = trimmed ? trimmed.split(/[。!?\.\!\?]/).filter((s) => s.trim()) : [];
  const hits = keywords.filter((k) => trimmed.includes(k));
  const coverage = keywords.length > 0 ? hits.length / keywords.length : 0;

  // 内容覆盖 35%
  const content = Math.round((coverage * 70 + Math.min(30, length / 5)) * 0.35 * 10) / 10;
  // 结构 20% — 至少 2-3 句,STAR 关键词
  const hasStar = /(首先|其次|最后|STAR|情境|任务|行动|结果|因此|所以|结果)/.test(trimmed);
  const structure = Math.round(
    (Math.min(1, sentences.length / 4) * 0.6 + (hasStar ? 0.4 : 0)) * 100 * 0.2 * 10,
  ) / 10;
  // 深度 20% — 字数 + 信息密度
  const depth = Math.round(Math.min(100, length / 1.2) * 0.2 * 10) / 10;
  // 流利度 15% — 句子平均长度
  const avgLen = sentences.length ? length / sentences.length : 0;
  const fluency = Math.round(Math.min(100, avgLen * 1.2) * 0.15 * 10) / 10;
  // 相关性 10%
  const relevance = Math.round(Math.min(100, coverage * 100 + (length > 30 ? 10 : 0)) * 0.1 * 10) / 10;

  const score = Math.round((content + structure + depth + fluency + relevance) * 10) / 10;
  const band: AnswerEntry["band"] =
    score >= 75 ? "excellent" : score >= 60 ? "good" : score >= 40 ? "fair" : "weak";

  const misses = keywords.filter((k) => !trimmed.includes(k));
  let feedback = "";
  if (band === "excellent") feedback = "回答覆盖度高、结构清晰、信息密度足,继续保持。";
  else if (band === "good")
    feedback = "回答整体不错,可以再补充量化数据或具体细节,让亮点更突出。";
  else if (band === "fair")
    feedback = "回答有一定基础,建议:1) 显式使用 STAR 结构;2) 多举具体数字;3) 覆盖更多关键概念。";
  else feedback = "回答过于简短,建议先列出 3-4 个要点,再展开;关注题目关键词并尽量覆盖。";

  return {
    score,
    band,
    feedback,
    hits,
    misses,
  };
}

export default function InterviewPrepPage(props: { params: Promise<{ role_id: string }> }) {
  const { role_id: roleId } = use(props.params);
  const router = useRouter();
  const meta = ROLE_META[roleId] || { label: roleId, icon: "💼", summary: "通用岗位准备" };
  const questions = useMemo(() => buildQuestions(roleId), [roleId]);
  const [activeIdx, setActiveIdx] = useState(0);
  const [answers, setAnswers] = useState<Record<string, AnswerEntry>>({});
  const [text, setText] = useState("");
  const [provider, setProvider] = useState<string | undefined>();
  const [report, setReport] = useState<PrepReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const textRef = useRef<HTMLTextAreaElement | null>(null);

  const answeredCount = Object.keys(answers).length;
  const activeQ = questions[activeIdx];
  const activeAnswer = activeQ ? answers[activeQ.id] : undefined;

  // 切换题目时清空输入:用 key 强制重挂载输入区,避免在渲染期写 ref
  const answerInputKey = `answer-input-${activeIdx}`;

  function handleSave() {
    if (!activeQ) return;
    if (!text.trim()) {
      setError("请先输入内容,或使用语音回答。");
      return;
    }
    setError(null);
    const ev = evaluate(text, activeQ.keywords);
    const entry: AnswerEntry = {
      question_id: activeQ.id,
      text: text.trim(),
      provider,
      char_count: text.trim().length,
      word_count: text.trim() ? text.trim().split(/\s+/).filter(Boolean).length : 0,
      submitted_at: new Date().toISOString(),
      ...ev,
    };
    setAnswers((prev) => ({ ...prev, [activeQ.id]: entry }));
  }

  function handleNext() {
    if (activeIdx + 1 < questions.length) {
      setActiveIdx(activeIdx + 1);
    } else {
      generateReport();
    }
  }

  function handlePrev() {
    if (activeIdx > 0) setActiveIdx(activeIdx - 1);
  }

  function handleVoice(textFromVoice: string, voiceProvider: string) {
    setText((prev) => (prev ? prev + "\n" + textFromVoice : textFromVoice).trim());
    setProvider(voiceProvider);
    setError(null);
  }

  function generateReport() {
    const entries = questions
      .map((q) => answers[q.id])
      .filter(Boolean) as AnswerEntry[];
    if (entries.length === 0) return;
    const totalScore = entries.reduce((s, e) => s + e.score, 0);
    const overall = Math.round((totalScore / entries.length) * 10) / 10;
    const band: AnswerEntry["band"] =
      overall >= 75 ? "excellent" : overall >= 60 ? "good" : overall >= 40 ? "fair" : "weak";
    // 5 维统计
    const radar = {
      content: Math.round(
        (entries.reduce((s, e) => s + e.hits.length, 0) / Math.max(1, entries.length * 3)) * 100,
      ),
      structure: Math.round(
        (entries.filter((e) => /(首先|其次|最后|结果|STAR|情境|任务|行动)/.test(e.text)).length /
          entries.length) * 100,
      ),
      depth: Math.round(
        (entries.reduce((s, e) => s + Math.min(100, e.char_count / 1.2), 0) / entries.length),
      ),
      fluency: Math.round(
        (entries.reduce((s, e) => {
          const sentences = e.text.split(/[。!?\.\!\?]/).filter(Boolean);
          return s + Math.min(100, (sentences.length ? e.char_count / sentences.length : 0) * 1.2);
        }, 0) / entries.length),
      ),
      relevance: Math.round(
        (entries.reduce((s, e) => s + e.hits.length, 0) /
          Math.max(1, entries.reduce((s, e) => s + e.hits.length + e.misses.length, 0))) * 100,
      ),
    };
    const summary =
      band === "excellent"
        ? `你的 10 题准备完成度很高,平均 ${overall.toFixed(1)} 分。建议进入正式 AI 模拟面试做最终验证。`
        : band === "good"
        ? `整体完成度不错,平均 ${overall.toFixed(1)} 分。可以针对"待提升"维度再练一轮,然后进入正式面试。`
        : band === "fair"
        ? `回答有一定框架但深度不足,平均 ${overall.toFixed(1)} 分。建议重做"行为"和"技术"两类题目,显式使用 STAR + 数字。`
        : `回答整体偏短,平均 ${overall.toFixed(1)} 分。建议每题先列 3-4 个要点再展开,并尽量覆盖题目关键词。`;

    const strengths: string[] = [];
    if (radar.content >= 60) strengths.push("关键词覆盖度好,说明你抓住了题目的核心考察点。");
    if (radar.structure >= 50) strengths.push("回答有清晰的结构,显式使用了 STAR 或类似的表达框架。");
    if (radar.depth >= 60) strengths.push("信息密度足,能展开具体的项目或技术细节。");
    if (strengths.length === 0) strengths.push("你已经迈出了练习的第一步,坚持做下去一定会有提升。");

    const improvements: string[] = [];
    if (radar.content < 50) improvements.push("扩大关键词覆盖:每题作答前列出 5-6 个相关概念,再组织答案。");
    if (radar.structure < 50) improvements.push("使用 STAR 法则(Situation / Task / Action / Result)来组织行为类问题。");
    if (radar.depth < 50) improvements.push("用具体数字 + 案例来支撑观点,例如 \"提升 32%\" 比 \"明显提升\" 有力得多。");
    if (radar.fluency < 50) improvements.push("口语化练习:用 VoiceRecorder 把答案录下来,听回放检查逻辑连贯性。");
    if (radar.relevance < 50) improvements.push("回答前先复述题目关键词,确保每段都扣题,避免跑题。");
    if (improvements.length === 0) improvements.push("继续保持,可在正式 AI 模拟面试中挑战更高难度的追问。");

    setReport({
      role: roleId,
      role_label: meta.label,
      generated_at: new Date().toISOString(),
      total_questions: questions.length,
      answered: entries.length,
      overall,
      band,
      radar,
      summary,
      strengths,
      improvements,
      per_question: entries,
    });
  }

  function resetAll() {
    setAnswers({});
    setActiveIdx(0);
    setReport(null);
    setText("");
  }

  // 报告视图
  if (report) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-slate-50 to-sky-50">
        <header className="bg-white border-b px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold flex items-center gap-2">
              <span aria-hidden>📊</span> 准备报告 · {meta.label}
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              基于 {report.answered} / {report.total_questions} 题的回答生成
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={resetAll}
              className="text-sm text-sky-600 hover:text-sky-800"
            >
              ↺ 再练一轮
            </button>
            <Link
              href={`/jobseeker/interview-prep/${roleId}`}
              className="text-sm text-slate-500 hover:text-slate-700"
            >
              切换岗位
            </Link>
            <button
              onClick={() => router.push("/jobseeker/interview")}
              className="text-sm text-slate-500 hover:text-slate-700"
            >
              返回面试中心
            </button>
          </div>
        </header>
        <div className="max-w-5xl mx-auto p-6 space-y-5" data-testid="prep-report">
          <section className="bg-white rounded-2xl shadow-sm p-5">
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="text-xl font-semibold">综合评分</h2>
              <span className={`px-2.5 py-1 rounded-full text-xs ${BAND_COLOR[report.band]}`}>
                {BAND_LABEL[report.band]}
              </span>
              <span className="ml-auto text-3xl font-bold text-slate-900">
                {report.overall.toFixed(1)}
              </span>
            </div>
            <p className="mt-3 text-sm text-slate-700 leading-relaxed">{report.summary}</p>
          </section>

          <section className="bg-white rounded-2xl shadow-sm p-5">
            <h3 className="text-sm font-semibold text-slate-800 mb-3">五维评分</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <Radar data={report.radar} />
              <div className="space-y-2">
                {([
                  ["content", "关键词覆盖"],
                  ["structure", "结构化表达"],
                  ["depth", "信息深度"],
                  ["fluency", "语言流畅"],
                  ["relevance", "切题相关"],
                ] as [keyof PrepReport["radar"], string][]).map(([k, label]) => (
                  <div key={k} className="rounded-lg border border-slate-200 p-3">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-slate-700">{label}</span>
                      <span className="font-bold text-slate-900">
                        {Math.round(report.radar[k])}
                      </span>
                    </div>
                    <div className="mt-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className={`h-full ${
                          report.radar[k] >= 75
                            ? "bg-emerald-500"
                            : report.radar[k] >= 55
                            ? "bg-sky-500"
                            : report.radar[k] >= 40
                            ? "bg-amber-500"
                            : "bg-rose-500"
                        }`}
                        style={{ width: `${Math.min(100, report.radar[k])}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-white rounded-2xl shadow-sm p-5">
              <h3 className="text-sm font-semibold text-emerald-700 mb-2">亮点</h3>
              <ul className="space-y-1 text-sm text-slate-700">
                {report.strengths.map((s, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-emerald-500">✓</span>
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="bg-white rounded-2xl shadow-sm p-5">
              <h3 className="text-sm font-semibold text-amber-700 mb-2">待提升</h3>
              <ul className="space-y-1 text-sm text-slate-700">
                {report.improvements.map((s, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-amber-500">→</span>
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            </div>
          </section>

          <section className="bg-white rounded-2xl shadow-sm p-5">
            <h3 className="text-sm font-semibold text-slate-800 mb-3">逐题回顾</h3>
            <ol className="space-y-3">
              {report.per_question.map((e, i) => {
                const q = questions.find((qq) => qq.id === e.question_id);
                if (!q) return null;
                return (
                  <li
                    key={e.question_id}
                    className="rounded-xl border border-slate-200 p-3"
                    data-testid={`prep-q-${q.id}`}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-500">
                        {q.kind_label}
                      </span>
                      <span className="font-medium text-slate-800">
                        Q{i + 1} · {q.title}
                      </span>
                      <span className={`text-xs px-1.5 py-0.5 rounded ${BAND_COLOR[e.band]}`}>
                        {BAND_LABEL[e.band]} · {e.score.toFixed(1)}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-slate-600 whitespace-pre-wrap">
                      {e.text.length > 200 ? e.text.slice(0, 200) + "…" : e.text}
                    </p>
                    {e.hits.length > 0 && (
                      <p className="mt-1 text-xs text-emerald-700">
                        ✓ 命中关键词: {e.hits.join("、")}
                      </p>
                    )}
                    {e.misses.length > 0 && (
                      <p className="mt-1 text-xs text-amber-700">
                        ⚠ 未覆盖: {e.misses.slice(0, 6).join("、")}
                        {e.misses.length > 6 ? "…" : ""}
                      </p>
                    )}
                    <p className="mt-1 text-xs text-slate-500 italic">「{e.feedback}」</p>
                  </li>
                );
              })}
            </ol>
          </section>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b">
        <div className="max-w-5xl mx-auto px-6 py-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
              <span aria-hidden>{meta.icon}</span> 角色准备 · {meta.label}
            </h1>
            <p className="text-sm text-slate-500 mt-1">{meta.summary}</p>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <Link
              href="/jobseeker/interview"
              className="text-slate-500 hover:text-slate-700"
            >
              ← 面试中心
            </Link>
          </div>
        </div>
      </header>

      <div className="max-w-5xl mx-auto p-6 space-y-4">
        {/* 进度条 */}
        <section className="bg-white rounded-2xl shadow-sm p-4" aria-label="答题进度">
          <div className="flex items-center justify-between text-xs text-slate-500 mb-2">
            <span>第 {activeIdx + 1} / {questions.length} 题</span>
            <span>已完成 {answeredCount} 题</span>
          </div>
          <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-sky-500 transition-all"
              style={{ width: `${((activeIdx + 1) / questions.length) * 100}%` }}
              role="progressbar"
              aria-valuenow={activeIdx + 1}
              aria-valuemin={1}
              aria-valuemax={questions.length}
            />
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {questions.map((q, i) => {
              const done = !!answers[q.id];
              const active = i === activeIdx;
              return (
                <button
                  key={q.id}
                  onClick={() => setActiveIdx(i)}
                  className={`min-w-8 h-8 px-2 rounded-full text-xs flex items-center justify-center ${
                    active
                      ? "bg-sky-600 text-white"
                      : done
                      ? "bg-emerald-100 text-emerald-700"
                      : "bg-slate-100 text-slate-500"
                  }`}
                  aria-label={`第 ${i + 1} 题 ${done ? "已完成" : "未完成"}`}
                >
                  {i + 1}
                </button>
              );
            })}
          </div>
        </section>

        {activeQ && (
          <section
            className="bg-white rounded-2xl shadow-sm p-5 space-y-4"
            data-testid="prep-question"
            aria-label="当前题目"
          >
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-500">
                {activeQ.kind_label}
              </span>
              <span className="text-xs text-slate-400">
                建议 {Math.round(activeQ.expected_seconds / 60)} 分钟
              </span>
            </div>
            <h2 className="text-lg font-semibold text-slate-900">{activeQ.title}</h2>
            <p className="text-slate-700 leading-relaxed">{activeQ.prompt}</p>
            {activeQ.hints.length > 0 && (
              <ul className="text-xs text-slate-500 list-disc pl-4 space-y-0.5">
                {activeQ.hints.map((h, i) => (
                  <li key={i}>{h}</li>
                ))}
              </ul>
            )}
            {activeQ.keywords.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                <span className="text-xs text-slate-500">命中关键词:</span>
                {activeQ.keywords.map((k) => (
                  <span
                    key={k}
                    className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-slate-50 text-slate-600 border border-slate-200"
                  >
                    {k}
                  </span>
                ))}
              </div>
            )}

            {activeAnswer ? (
              <div className="space-y-3">
                <div
                  className={`rounded-xl border p-4 ${
                    activeAnswer.band === "excellent"
                      ? "bg-emerald-50 border-emerald-200"
                      : activeAnswer.band === "good"
                      ? "bg-sky-50 border-sky-200"
                      : activeAnswer.band === "fair"
                      ? "bg-amber-50 border-amber-200"
                      : "bg-rose-50 border-rose-200"
                  }`}
                  data-testid="prep-result"
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      className={`text-xs px-2 py-0.5 rounded font-medium ${BAND_COLOR[activeAnswer.band]}`}
                    >
                      {BAND_LABEL[activeAnswer.band]} · {activeAnswer.score.toFixed(1)} 分
                    </span>
                    <span className="text-xs text-slate-500">
                      {activeAnswer.char_count} 字 · {activeAnswer.word_count} 词
                      {activeAnswer.provider && ` · 转写自 ${activeAnswer.provider}`}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-slate-700 italic">「{activeAnswer.feedback}」</p>
                  {activeAnswer.hits.length > 0 && (
                    <p className="mt-1 text-xs text-emerald-700">
                      ✓ 命中: {activeAnswer.hits.join("、")}
                    </p>
                  )}
                  {activeAnswer.misses.length > 0 && (
                    <p className="mt-1 text-xs text-amber-700">
                      ⚠ 建议补: {activeAnswer.misses.slice(0, 6).join("、")}
                    </p>
                  )}
                </div>
                <details className="text-xs text-slate-500">
                  <summary className="cursor-pointer">查看你的回答</summary>
                  <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">
                    {activeAnswer.text}
                  </p>
                </details>
              </div>
            ) : (
              <AnswerInput
                key={answerInputKey}
                ref={textRef}
                expectedSeconds={activeQ.expected_seconds}
                onVoice={handleVoice}
                onError={setError}
                onChangeText={setText}
                onSnapshot={setText}
              />
            )}

            {error && (
              <div
                className="bg-rose-50 text-rose-700 text-sm rounded p-2"
                role="alert"
              >
                {error}
              </div>
            )}

            <div className="flex flex-wrap items-center justify-between gap-2 pt-2">
              <button
                onClick={handlePrev}
                disabled={activeIdx === 0}
                className="px-4 py-2 rounded-lg bg-slate-200 hover:bg-slate-300 disabled:opacity-50 text-sm"
              >
                ← 上一题
              </button>
              <div className="flex gap-2">
                {!activeAnswer && (
                  <button
                    onClick={handleSave}
                    disabled={!text.trim()}
                    data-testid="save-answer"
                    className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm font-medium disabled:opacity-50 hover:bg-emerald-700"
                  >
                    保存本题
                  </button>
                )}
                <button
                  onClick={handleNext}
                  data-testid="next-question"
                  className="px-4 py-2 rounded-lg bg-sky-600 text-white text-sm font-medium hover:bg-sky-700"
                >
                  {activeIdx + 1 === questions.length ? "生成反馈报告 →" : "下一题 →"}
                </button>
              </div>
            </div>
          </section>
        )}

        {answeredCount >= questions.length && !report && (
          <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-4 text-sm text-emerald-800 flex items-center justify-between">
            <span>🎉 全部 {questions.length} 题已作答,可以生成反馈报告了。</span>
            <button
              onClick={generateReport}
              className="px-4 py-1.5 rounded-lg bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700"
              data-testid="generate-report"
            >
              生成反馈报告
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

interface AnswerInputProps {
  expectedSeconds: number;
  onVoice: (text: string, provider: string) => void;
  onError: (msg: string) => void;
  onChangeText: (text: string) => void;
  onSnapshot: (text: string) => void;
}

const AnswerInput = forwardRef<HTMLTextAreaElement, AnswerInputProps>(function AnswerInput(
  { expectedSeconds, onVoice, onError, onChangeText },
  ref,
) {
  const [text, setText] = useState("");
  useImperativeHandle(ref, () => document.createElement("textarea"));
  return (
    <>
      <textarea
        ref={(el) => {
          if (typeof ref === "function") ref(el);
          else if (ref) (ref as React.MutableRefObject<HTMLTextAreaElement | null>).current = el;
        }}
        data-testid="prep-text"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          onChangeText(e.target.value);
        }}
        rows={6}
        placeholder="在此输入你的回答,或使用下方「语音」按钮录入。提示:覆盖更多关键词 + 显式使用 STAR 结构 + 给出具体数字。…"
        className="w-full rounded-xl border border-slate-300 p-3 text-sm focus:border-sky-500 focus:ring-1 focus:ring-sky-200 outline-none"
        aria-label="回答输入框"
      />
      <div className="grid md:grid-cols-2 gap-3">
        <VoiceRecorder
          onTranscript={(t, p) => {
            setText((prev) => (prev ? prev + "\n" + t : t).trim());
            onVoice(t, p);
          }}
          onError={onError}
          maxDurationSec={Math.max(60, expectedSeconds)}
        />
        <div className="text-xs text-slate-500 leading-relaxed bg-slate-50 rounded-xl p-3">
          <p className="font-medium text-slate-700 mb-1">作答小贴士</p>
          <ul className="list-disc pl-4 space-y-0.5">
            <li>先列 3-4 个要点,再展开论述。</li>
            <li>使用具体数字(百分比 / 时间 / 金额)。</li>
            <li>行为题用 STAR(情境/任务/行动/结果)。</li>
            <li>回答完毕点「保存本题」评估,再点「下一题」。</li>
          </ul>
        </div>
      </div>
    </>
  );
});

function Radar({ data }: { data: PrepReport["radar"] }) {
  const size = 220;
  const cx = size / 2;
  const cy = size / 2;
  const r = 80;
  const keys = ["content", "structure", "depth", "fluency", "relevance"] as const;
  const labels: Record<typeof keys[number], string> = {
    content: "覆盖",
    structure: "结构",
    depth: "深度",
    fluency: "流畅",
    relevance: "切题",
  };
  const angleStep = (Math.PI * 2) / keys.length;
  const points = keys.map((k, i) => {
    const v = Math.max(0, Math.min(100, data[k])) / 100;
    const a = -Math.PI / 2 + i * angleStep;
    return [cx + Math.cos(a) * r * v, cy + Math.sin(a) * r * v] as const;
  });
  const polygon = points.map((p) => p.join(",")).join(" ");
  const grid = [0.25, 0.5, 0.75, 1].map((scale) =>
    keys
      .map((_, i) => {
        const a = -Math.PI / 2 + i * angleStep;
        return [cx + Math.cos(a) * r * scale, cy + Math.sin(a) * r * scale].join(",");
      })
      .join(" "),
  );
  return (
    <svg
      viewBox={`0 0 ${size} ${size}`}
      className="w-full max-w-[260px] mx-auto"
      aria-label="五维评分雷达图"
    >
      <defs>
        <radialGradient id="prep-radar-fill" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#34d399" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#0ea5e9" stopOpacity="0.3" />
        </radialGradient>
      </defs>
      {grid.map((g, idx) => (
        <polygon key={idx} points={g} fill="none" stroke="#e2e8f0" strokeWidth="1" />
      ))}
      {keys.map((k, i) => {
        const a = -Math.PI / 2 + i * angleStep;
        return (
          <line
            key={k}
            x1={cx}
            y1={cy}
            x2={cx + Math.cos(a) * r}
            y2={cy + Math.sin(a) * r}
            stroke="#e2e8f0"
            strokeWidth="1"
          />
        );
      })}
      <polygon points={polygon} fill="url(#prep-radar-fill)" stroke="#0284c7" strokeWidth="2" />
      {keys.map((k, i) => {
        const v = Math.round(data[k]);
        const a = -Math.PI / 2 + i * angleStep;
        const lx = cx + Math.cos(a) * (r + 18);
        const ly = cy + Math.sin(a) * (r + 18);
        return (
          <g key={k}>
            <text
              x={lx}
              y={ly}
              fontSize="11"
              textAnchor="middle"
              dominantBaseline="middle"
              className="fill-slate-700"
            >
              {labels[k]}
            </text>
            <text
              x={lx}
              y={ly + 12}
              fontSize="10"
              textAnchor="middle"
              dominantBaseline="middle"
              className="fill-slate-500"
            >
              {v}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
