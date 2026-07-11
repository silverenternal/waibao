"use client";

import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { SkillDemand } from "@/lib/api-market";

interface Props {
  data: SkillDemand[];
  height?: number;
  limit?: number;
}

export function HotSkillsRadar({ data, height = 320, limit = 8 }: Props) {
  if (!data || data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-sm text-muted-foreground"
        style={{ height }}
      >
        暂无热门技能数据
      </div>
    );
  }

  // 取 top N + 截断 skill 名过长
  const chart = data.slice(0, limit).map((s) => ({
    skill: s.skill.length > 8 ? `${s.skill.slice(0, 7)}…` : s.skill,
    fullSkill: s.skill,
    score: s.demand_score,
    job_count: s.job_count,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <RadarChart data={chart} cx="50%" cy="50%" outerRadius="75%">
        <PolarGrid stroke="#cbd5e1" />
        <PolarAngleAxis dataKey="skill" tick={{ fontSize: 12 }} />
        <PolarRadiusAxis
          angle={90}
          domain={[0, 100]}
          tick={{ fontSize: 10 }}
          stroke="#94a3b8"
        />
        <Tooltip
          formatter={(v, _name, props: any) => [
            `${typeof v === "number" ? v.toFixed(0) : 0} 分 · ${props.payload.job_count ?? 0} 岗位`,
            props.payload.fullSkill,
          ]}
        />
        <Radar
          name="需求热度"
          dataKey="score"
          stroke="#6366f1"
          fill="#6366f1"
          fillOpacity={0.45}
        />
      </RadarChart>
    </ResponsiveContainer>
  );
}

export default HotSkillsRadar;