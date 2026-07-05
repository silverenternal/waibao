"use client";

import { useState } from "react";

export default function EmployerHome() {
  const [activeModule, setActiveModule] = useState<string>("vision");

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="bg-white border-b px-6 py-4">
        <h1 className="text-xl font-semibold">🏢 HR 工作台</h1>
        <p className="text-sm text-slate-500 mt-1">我是你的真诚 HR 助手</p>
      </div>

      <div className="max-w-6xl mx-auto p-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          {[
            { id: "vision", icon: "🎯", label: "愿景战略" },
            { id: "compliance", icon: "✅", label: "资质管理" },
            { id: "talent", icon: "👥", label: "人才需求" },
            { id: "spec", icon: "📋", label: "JD 细化" },
            { id: "policy", icon: "📜", label: "规章制度" },
            { id: "multi", icon: "💬", label: "多方对话" },
            { id: "service", icon: "🛎️", label: "HR 服务" },
            { id: "match", icon: "🤝", label: "双向匹配" },
          ].map((m) => (
            <button
              key={m.id}
              onClick={() => setActiveModule(m.id)}
              className={`p-4 rounded-xl text-left transition ${
                activeModule === m.id
                  ? "bg-blue-600 text-white shadow-md"
                  : "bg-white hover:shadow"
              }`}
            >
              <div className="text-2xl">{m.icon}</div>
              <div className="font-medium mt-1">{m.label}</div>
            </button>
          ))}
        </div>

        {activeModule === "vision" && <VisionModule />}
        {activeModule === "compliance" && <ComplianceModule />}
        {activeModule === "talent" && <TalentBriefModule />}
        {activeModule === "spec" && <JobSpecModule />}
        {activeModule === "policy" && <PolicyModule />}
        {activeModule === "multi" && <MultipartyModule />}
        {activeModule === "service" && <HRServiceModule />}
        {activeModule === "match" && <MatchingModule />}
      </div>
    </div>
  );
}

function ModuleFrame({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-2xl shadow-sm p-6">
      <h2 className="text-lg font-semibold mb-4">{title}</h2>
      {children}
    </div>
  );
}

function TextResult({ text }: { text: string }) {
  return (
    <div className="mt-4 p-4 bg-slate-50 rounded-xl whitespace-pre-wrap text-sm">
      {text || "智能体还没有回复"}
    </div>
  );
}

function VisionModule() {
  const [text, setText] = useState("");
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);
  async function submit() {
    setLoading(true);
    try {
      const token = localStorage.getItem("sb_token") || "";
      const r = await fetch("/api/vision/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ text }),
      });
      const data = await r.json();
      setResult(data.text || "");
    } finally { setLoading(false); }
  }
  return (
    <ModuleFrame title="🎯 愿景 / 规划 / 战略 / 战术">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="描述公司愿景(3-5 年想成为什么)、1 年规划、年度战略、本季度战术..."
        className="w-full border rounded-xl p-3 min-h-32 focus:ring-2 focus:ring-blue-500 focus:outline-none"
      />
      <button onClick={submit} disabled={loading} className="mt-3 px-5 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50">
        {loading ? "分析中..." : "提交分析"}
      </button>
      <TextResult text={result} />
    </ModuleFrame>
  );
}

function ComplianceModule() {
  const [url, setUrl] = useState("");
  const [type, setType] = useState("business_license");
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);
  async function submit() {
    setLoading(true);
    try {
      const token = localStorage.getItem("sb_token") || "";
      const r = await fetch("/api/compliance/upload", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ file_url: url, credential_type: type }),
      });
      const data = await r.json();
      setResult(data.text || "");
    } finally { setLoading(false); }
  }
  return (
    <ModuleFrame title="✅ 资质上传 + 智能验证">
      <select value={type} onChange={(e) => setType(e.target.value)} className="border rounded p-2 w-full mb-2">
        <option value="business_license">营业执照</option>
        <option value="legal_id">法人身份证</option>
        <option value="industry_cert">行业资质</option>
        <option value="tax_cert">税务证明</option>
      </select>
      <input
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="上传文件 URL"
        className="w-full border rounded p-2 mb-2"
      />
      <button onClick={submit} disabled={loading} className="px-5 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50">
        {loading ? "审核中..." : "审核"}
      </button>
      <TextResult text={result} />
    </ModuleFrame>
  );
}

function TalentBriefModule() {
  const [text, setText] = useState("");
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);
  async function submit() {
    setLoading(true);
    try {
      const token = localStorage.getItem("sb_token") || "";
      const r = await fetch("/api/talent-brief/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ text }),
      });
      const data = await r.json();
      setResult(data.text || "");
    } finally { setLoading(false); }
  }
  return (
    <ModuleFrame title="👥 人才框架描述">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="描述所需人才的行业、职级、价值观、潜力方向..."
        className="w-full border rounded-xl p-3 min-h-32"
      />
      <button onClick={submit} disabled={loading} className="mt-3 px-5 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50">
        {loading ? "提炼中..." : "提炼"}
      </button>
      <TextResult text={result} />
    </ModuleFrame>
  );
}

function JobSpecModule() {
  const [text, setText] = useState("");
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);
  async function submit() {
    setLoading(true);
    try {
      const token = localStorage.getItem("sb_token") || "";
      const r = await fetch("/api/job-spec/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ text }),
      });
      const data = await r.json();
      setResult(data.text || "");
    } finally { setLoading(false); }
  }
  return (
    <ModuleFrame title="📋 JD 细化(部门负责人)">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="岗位职责、必备技能、加分项、协作风格、汇报关系..."
        className="w-full border rounded-xl p-3 min-h-32"
      />
      <button onClick={submit} disabled={loading} className="mt-3 px-5 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50">
        {loading ? "生成中..." : "生成 JD"}
      </button>
      <TextResult text={result} />
    </ModuleFrame>
  );
}

function PolicyModule() {
  const [text, setText] = useState("");
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);
  async function submit() {
    setLoading(true);
    try {
      const token = localStorage.getItem("sb_token") || "";
      const r = await fetch("/api/policy/upload", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ text, category: "attendance", organisation_id: "demo-org" }),
      });
      const data = await r.json();
      setResult(data.text || "");
    } finally { setLoading(false); }
  }
  return (
    <ModuleFrame title="📜 规章制度上传">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="粘贴制度文本(考勤/请假/报销/晋升/福利等)..."
        className="w-full border rounded-xl p-3 min-h-32"
      />
      <button onClick={submit} disabled={loading} className="mt-3 px-5 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50">
        {loading ? "解析中..." : "解析入库"}
      </button>
      <TextResult text={result} />
    </ModuleFrame>
  );
}

function MultipartyModule() {
  const [text, setText] = useState("");
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);
  async function submit() {
    setLoading(true);
    try {
      const token = localStorage.getItem("sb_token") || "";
      const inputs = text.split("\n\n").map((p) => {
        const [role, ...msg] = p.split(":");
        return { role: role?.trim() || "unknown", message: msg.join(":").trim(), user_id: "u1" };
      });
      const r = await fetch("/api/multiparty/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ inputs }),
      });
      const data = await r.json();
      setResult(data.text || "");
    } finally { setLoading(false); }
  }
  return (
    <ModuleFrame title="💬 多方对话协调">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={"格式:\nboss: 我们需要尽快招到大牛\nhr: 预算有限,最多 30k\ndept_head: 我只要 5 年以上经验"}
        className="w-full border rounded-xl p-3 min-h-32"
      />
      <button onClick={submit} disabled={loading} className="mt-3 px-5 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50">
        {loading ? "汇总中..." : "汇总决策"}
      </button>
      <TextResult text={result} />
    </ModuleFrame>
  );
}

function HRServiceModule() {
  const [text, setText] = useState("");
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);
  async function submit() {
    setLoading(true);
    try {
      const token = localStorage.getItem("sb_token") || "";
      const r = await fetch("/api/realtime/invoke", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ text, agent_name: "hr_service_agent" }),
      });
      const data = await r.json();
      setResult(data.text || "");
    } finally { setLoading(false); }
  }
  return (
    <ModuleFrame title="🛎️ HR 全生命周期服务">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="员工问题: 假期余额 / 报销流程 / 晋升通道 / 入职材料..."
        className="w-full border rounded-xl p-3 min-h-32"
      />
      <button onClick={submit} disabled={loading} className="mt-3 px-5 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50">
        {loading ? "处理中..." : "提交"}
      </button>
      <TextResult text={result} />
    </ModuleFrame>
  );
}

function MatchingModule() {
  const [candidateId, setCandidateId] = useState("");
  const [roleId, setRoleId] = useState("");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  async function submit() {
    setLoading(true);
    try {
      const token = localStorage.getItem("sb_token") || "";
      const r = await fetch(
        `/api/two-way-match/compute?candidate_id=${candidateId}&role_id=${roleId}`,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } }
      );
      const data = await r.json();
      setResult(data);
    } finally { setLoading(false); }
  }
  return (
    <ModuleFrame title="🤝 双向匹配计算">
      <div className="grid grid-cols-2 gap-3">
        <input value={candidateId} onChange={(e) => setCandidateId(e.target.value)} placeholder="候选人 ID" className="border rounded p-2" />
        <input value={roleId} onChange={(e) => setRoleId(e.target.value)} placeholder="岗位 ID" className="border rounded p-2" />
      </div>
      <button onClick={submit} disabled={loading} className="mt-3 px-5 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50">
        {loading ? "计算中..." : "计算双向分"}
      </button>
      {result && (
        <div className="mt-4 grid grid-cols-3 gap-3">
          <div className="bg-blue-50 p-4 rounded-xl text-center">
            <div className="text-xs text-slate-500">求职者→岗位</div>
            <div className="text-2xl font-bold text-blue-700">{(result.candidate_to_role * 100).toFixed(0)}%</div>
          </div>
          <div className="bg-green-50 p-4 rounded-xl text-center">
            <div className="text-xs text-slate-500">岗位→求职者</div>
            <div className="text-2xl font-bold text-green-700">{(result.role_to_candidate * 100).toFixed(0)}%</div>
          </div>
          <div className="bg-purple-50 p-4 rounded-xl text-center">
            <div className="text-xs text-slate-500">调和值</div>
            <div className="text-2xl font-bold text-purple-700">{(result.harmonic_score * 100).toFixed(0)}%</div>
          </div>
        </div>
      )}
    </ModuleFrame>
  );
}