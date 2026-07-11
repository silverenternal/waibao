"""求职者侧 - Profile Agent.

需求 1.1: 智能/知心朋友,接收求职者学历等信息.
通过对话式交互收集/校验/补全资料。

支持 ctx.file_url — 简历图片/PDF 上传后自动走 OCR 抽取并合并进画像。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient
from agents.toolkit import llm_call

logger = logging.getLogger("recruittech.agents.jobseeker.profile")


PROFILE_INTAKE_PROMPT = """你是求职者画像采集助手。

任务: 基于用户最新的输入,提取/更新画像字段,生成温和的追问(最多 2 个)。

要维护的画像字段:
- name (姓名)
- education (学历: degree + school + major + year)
- experience_years (工作年限)
- location (所在地)
- skills (技能列表)
- certifications (证书)
- portfolio (作品集)
- interests (兴趣方向)

输出 JSON:
{
  "updated_profile": { ... 字段 ... },
  "next_questions": ["问题1", "问题2"],
  "completion": 0.0 ~ 1.0,
  "warm_response": "给用户看的温暖回应"
}
"""


class ProfileAgent(BaseAgent):
    """对话式画像采集/补全 Agent."""

    name = "profile_agent"
    description = "求职者的知心朋友 + 画像采集助手(需求 1.1)"
    required_personas = ("jobseeker", "talent_partner", "admin")

    async def _maybe_ocr_resume(self, ctx: dict[str, Any]) -> dict[str, Any] | None:
        """如果 ctx 带 file_url,就走 OCR + LLM 抽取简历结构,返回 extracted dict."""
        file_url = ctx.get("file_url")
        if not file_url:
            return None
        try:
            # Late module import — 让 monkeypatch.setattr 可以生效
            from services import resume_parser as _rp

            parser = getattr(_rp, "parse_resume_from_url", None)
            if parser is None:  # pragma: no cover - defensive
                from services.resume_parser import parse_resume_from_url as parser

            parsed = await parser(
                file_url,
                llm=self.llm if isinstance(self.llm, LLMClient) else LLMClient(),
                hint=ctx.get("resume_hint"),
            )
            return parsed
        except Exception as e:  # noqa: BLE001
            logger.warning(f"profile_agent OCR/resume parse failed: {e}")
            return {"_error": str(e), "source_url": file_url}

    def _merge_resume_into_profile(self, profile: dict, parsed: dict) -> dict:
        """把 LLM 抽取出的 resume 字段 merge 进 profile。"""
        extracted = parsed.get("extracted") or {}
        basic = extracted.get("basic") if isinstance(extracted.get("basic"), dict) else {}
        merged = dict(profile)

        if basic:
            name = basic.get("name") if isinstance(basic.get("name"), str) else None
            if name and not merged.get("name"):
                merged["name"] = name
            for k in ("email", "phone", "location"):
                v = basic.get(k)
                if v and not merged.get(k):
                    merged[k] = v

        edu = extracted.get("education") or []
        if edu and not merged.get("education"):
            merged["education"] = edu

        skills = extracted.get("skills") or []
        if skills:
            existing = {s.get("name"): s for s in (merged.get("skills") or []) if isinstance(s, dict)}
            for s in skills:
                if isinstance(s, dict) and s.get("name") and s["name"] not in existing:
                    existing[s["name"]] = s
            merged["skills"] = list(existing.values())

        # raw_text & provenance
        merged.setdefault("_resume_source_url", parsed.get("source_url"))
        merged["_resume_raw_text_snippet"] = (parsed.get("raw_text") or "")[:300]
        merged["_resume_provider_chain"] = parsed.get("provider_chain", [])
        return merged

    async def _handle(self, agent_input: AgentInput) -> AgentOutput:
        text = agent_input.text
        ctx = agent_input.context or {}

        # 读已有画像
        existing = await self.recall(
            __import__("agents.runtime", fromlist=["MemoryScope"]).MemoryScope.long_term,
            key="profile",
            user_id=agent_input.user_id,
            default={},
        )

        # ---- 自动 OCR (new in T102) ----
        resume_parsed = await self._maybe_ocr_resume(ctx)
        if resume_parsed and "_error" not in resume_parsed:
            existing = self._merge_resume_into_profile(existing, resume_parsed)
        ocr_notice = ""
        if resume_parsed and "_error" in resume_parsed:
            ocr_notice = f"\n(注:简历解析失败 — {resume_parsed.get('_error', '未知错误')})"

        system = PROFILE_INTAKE_PROMPT
        user_msg = f"已有画像: {json.dumps(existing, ensure_ascii=False)}\n用户新输入: {text}{ocr_notice}"

        raw = await llm_call(self.llm or LLMClient(), user_msg, system=system, json_mode=True)

        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {"warm_response": raw, "next_questions": [], "updated_profile": {}, "completion": 0.5}

        # 合并画像
        updated = {**existing, **(result.get("updated_profile") or {})}
        await self.remember(
            __import__("agents.runtime", fromlist=["MemoryScope"]).MemoryScope.long_term,
            key="profile",
            value=updated,
            user_id=agent_input.user_id,
        )

        warm = result.get("warm_response", "好的,我记下了。")
        if resume_parsed and "_error" not in resume_parsed:
            warm = f"我从你上传的文件里抽取了关键信息。{warm}"

        return AgentOutput(
            agent_name=self.name,
            text=warm,
            artifacts={
                "updated_profile": updated,
                "next_questions": result.get("next_questions", []),
                "completion": result.get("completion", 0.5),
                "ocr_triggered": bool(resume_parsed),
                "ocr_provider": (resume_parsed or {}).get("ocr_provider"),
                "resume_extracted": (resume_parsed or {}).get("extracted"),
            },
            memory_writes=[{
                "scope": "long_term",
                "key": "profile",
                "value": updated,
            }],
        )
