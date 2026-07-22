"""Policy Agent - 规章制度上传 + RAG 检索.

需求 2.6: 管理部门上传上下班时间及相关规章制度.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import uuid4

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient
from agents.prompts import get_prompt as _get_prompt
from agents.toolkit import llm_call
from eventbus import emit

logger = logging.getLogger("recruittech.agents.employer.policy")


def _as_dict(raw: str | bytes) -> dict:
    """Defensively parse an LLM JSON payload into a dict.

    Local LLMs occasionally return a JSON array / scalar; the downstream
    ``result.get(...)`` calls would otherwise raise AttributeError. Non-dict
    payloads fall back to ``{}``.
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


POLICY_PROMPT = """你是企业制度管家。

上传/查询内容:
"{text}"
任务类型: {task_type}  // upload / query

请输出 JSON:
{{
  "items": [
    {{"category": "考勤/请假/...", "title": "制度标题", "content": "详细内容", "effective_from": "YYYY-MM-DD"}}
  ],
  "legal_risks": ["潜在法律风险"],
  "faq_version": [
    {{"question": "...", "answer": "..."}}
  ]
}}
"""


class PolicyAgent(BaseAgent):
    name = "policy_agent"
    description = "规章制度上传 + RAG 检索 (2.6)"
    required_personas = ("hr", "boss", "dept_head", "admin", "jobseeker")

    async def _handle(self, agent_input: AgentInput) -> AgentOutput:
        text = agent_input.text
        ctx = agent_input.context or {}
        task_type = ctx.get("task_type", "query")
        organisation_id = ctx.get("organisation_id", agent_input.user_id)

        # upload: 解析并入库
        if task_type == "upload":
            try:
                raw = await llm_call(
                    self.llm or LLMClient(),
                    _get_prompt("policy_agent", "system", default=POLICY_PROMPT).format(text=text, task_type="upload"),
                    system="你是 HR 制度专家。",
                    json_mode=True,
                )
                result = _as_dict(raw)
            except Exception:
                result = {}
            if not result:
                result = {"items": [{"category": "other", "title": "制度", "content": text[:500]}], "legal_risks": [], "faq_version": []}

            # 写入 company_policies
            for item in result.get("items", []):
                record = {
                    "organisation_id": organisation_id,
                    "category": item.get("category", "other"),
                    "title": item.get("title", ""),
                    "content": item.get("content", ""),
                    "effective_from": item.get("effective_from"),
                    "uploaded_by": agent_input.user_id,
                }
                try:
                    from api.deps import get_supabase_admin
                    supabase = get_supabase_admin()
                    supabase.table("company_policies").insert(record).execute()
                except Exception as e:
                    logger.warning(f"failed to persist policy: {e}")

            legal_warnings = ""
            if result.get("legal_risks"):
                legal_warnings = "\n\n⚠️ 法律风险提示:\n" + "\n".join(f"  - {x}" for x in result["legal_risks"])

            return AgentOutput(
                agent_name=self.name,
                text=f"✅ 制度已入库: {len(result.get('items', []))} 条" + legal_warnings,
                artifacts=result,
            )

        # query: 从数据库查询 + 生成 FAQ 风格回答
        try:
            from api.deps import get_supabase_admin
            supabase = get_supabase_admin()
            resp = (
                supabase.table("company_policies")
                .select("title, content, category")
                .eq("organisation_id", organisation_id)
                .or_(f"title.ilike.%{text[:20]}%,content.ilike.%{text[:20]}%")
                .limit(5)
                .execute()
            )
            candidates = resp.data or []
        except Exception:
            candidates = []

        # 契约 (2.6 制度 = 存文档 + AI引用): 若库里没有匹配制度,直接告知
        # 用户"暂无相关制度",而不是让 AI 在零引用下凭空编造答案 (silent-failure:
        # AI 看起来答了,实则无据可依).  上传后才有内容.
        if not candidates:
            return AgentOutput(
                agent_name=self.name,
                text=(
                    "暂未在制度库中找到与该问题匹配的条款。\n"
                    "如需查询,请先由管理部门上传相关制度文档;已有文档可换个关键词重试。"
                ),
                artifacts={"matched_policies": [], "query": text[:100]},
            )

        # LLM 生成回答 (只在有真实制度片段引用时才调用)
        raw = await llm_call(
            self.llm or LLMClient(),
            f"用户问题: {text}\n制度片段:\n" + "\n".join(
                f"- [{c.get('category') or '其他'}] {c.get('title') or ''}: "
                f"{str(c.get('content') or '')[:200]}"
                for c in candidates
            ),
            system="你是企业制度助手,回答必须引用上面的具体制度条款;无依据时请明确说明。",
        )

        # v6.0 EventBus — best-effort audit trail
        try:
            emit("audit.recorded", {
                "actor_id": agent_input.user_id,
                "action": "policy_lookup",
                "resource": "policy_doc",
                "before": None,
                "after": {"candidates": [c.get("title") for c in candidates][:3]},
            }, source="agent.policy")
        except Exception as _e:
            logger.debug("eventbus publish failed: %s", _e)

        return AgentOutput(
            agent_name=self.name,
            text=raw,
            artifacts={"matched_policies": [c.get("title") for c in candidates]},
        )