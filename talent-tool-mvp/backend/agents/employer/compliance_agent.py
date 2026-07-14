"""Compliance Agent - 资质上传 + 智能验证.

需求 2.2: 用人单位资质上传,智能验证真实性。

业务模块迁移:
    历史版本直接在 agent 内串联 OCR + lookup + LLM verdict.
    T103 改造后抽离到 services.compliance_service, 只剩 LLM 综合判定
    和 Supabase 持久化在 agent 内。

链路:
    file_url → OCR (registry OCR,失败降级 Vision)
            → ocr_data
            → compliance_service.verify_credential_against_lookup(ocr_data)
            → LLM verdict (trust_score / verified_fields / warnings / expiry_risk)
            → Supabase persist (company_credentials)
            → AgentOutput(text + artifacts)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import uuid4

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient
from agents.prompts import get_prompt as _get_prompt
from agents.toolkit import llm_call
from services.compliance_service import verify_credential_against_lookup
from eventbus import emit

logger = logging.getLogger("recruittech.agents.employer.compliance")

COMPLIANCE_PROMPT = """你是企业资质审核专家。

OCR 提取:
{ocr}

合规校验结果:
{verify}

请基于以上输入做最终综合判定,输出 JSON:
{{
  "trust_score": 0.0 ~ 1.0,
  "verified_fields": {{"company_name": "...", "credit_code": "...", "is_valid": true/false}},
  "missing_items": ["还缺什么材料"],
  "warnings": ["风险点"],
  "expiry_risk": true/false,
  "summary": "一句话审核结论"
}}
"""


class ComplianceAgent(BaseAgent):
    name = "compliance_agent"
    description = "资质上传 + 智能验证 (2.2)"
    required_personas = ("hr", "boss", "admin")

    async def _ocr_credential(self, file_url: str) -> dict:
        """走 OCR_PROVIDER 抽文字,失败时降级到 Vision OCR."""
        text = ""
        provider_used = None
        try:
            from providers.registry import get_ocr_provider

            provider = get_ocr_provider()
            provider_used = getattr(provider, "provider_name", "ocr")
            res = await provider.recognize_url(file_url)
            text = res.text or ""
        except Exception as e:  # noqa: BLE001
            logger.warning(f"compliance_agent OCR failed ({e}), trying vision fallback")
            text = ""
            provider_used = f"{provider_used}_failed"

        # Vision fallback
        if not text.strip():
            try:
                from providers.registry import get_vision_provider
                from providers.vision.base import ImageInput

                vision = get_vision_provider()
                img = ImageInput(url=file_url)
                text = await vision.ocr(img)
                provider_used = f"{provider_used or 'ocr'}_vision"
            except Exception as e:  # noqa: BLE001
                logger.warning(f"compliance_agent vision OCR fallback failed: {e}")
                text = ""

        return {"text": text, "provider": provider_used or "unknown"}

    async def _handle(self, agent_input: AgentInput) -> AgentOutput:
        ctx = agent_input.context or {}
        file_url = ctx.get("file_url")
        credential_type = ctx.get("credential_type", "business_license")
        expiry_at = ctx.get("expiry_at") or ctx.get("expiry_date")

        if not file_url:
            return AgentOutput(
                agent_name=self.name,
                text="请上传资质文件 (营业执照/法人身份证/行业资质等)。",
                artifacts={"stage": "awaiting_upload"},
            )

        # 1. OCR (走 providers/ocr,失败时降级到 vision)
        ocr = await self._ocr_credential(file_url)
        ocr_text = ocr.get("text", "") or ""
        ocr_provider = ocr.get("provider", "unknown")

        ocr_data = {
            "company_name": ctx.get("hint_company_name", ""),
            "credit_code": ctx.get("hint_credit_code", ""),
            "legal_rep": "",
            "registered_capital": "",
            "ocr_text_snippet": ocr_text[:300],
            "ocr_provider": ocr_provider,
        }

        # 2. 走 compliance_service 聚合: 信用代码校验 + lookup + 风险评分
        verify = await verify_credential_against_lookup(ocr_data)
        lookup_status = verify.get("lookup_status")
        cc_valid = verify.get("credit_code_valid")
        service_trust = verify.get("trust_score", 0.0)

        # 3. LLM 综合判定
        try:
            raw = await llm_call(
                self.llm or LLMClient(),
                "请审核",
                system=_get_prompt("compliance_agent", "system", default=COMPLIANCE_PROMPT).format(
                    ocr=json.dumps(ocr_data, ensure_ascii=False),
                    verify=json.dumps(verify, ensure_ascii=False),
                ),
                json_mode=True,
            )
            verdict = json.loads(raw)
        except Exception:
            verdict = {
                "trust_score": service_trust if cc_valid else 0.3,
                "verified_fields": {
                    **ocr_data,
                    "is_valid": bool(cc_valid),
                    "company_match": verify.get("company_match"),
                },
                "missing_items": ["建议补充法人身份证"],
                "warnings": list(verify.get("warnings") or []),
                "expiry_risk": False,
                "summary": verify.get("summary") or "基础验证通过",
            }

        # 4. 持久化
        record = {
            "id": str(uuid4()),
            "organisation_id": agent_input.user_id,
            "credential_type": credential_type,
            "file_url": file_url,
            "expiry_date": expiry_at,
            "verified": verdict.get("trust_score", 0) >= 0.6,
            "verified_at": datetime.utcnow().isoformat()
            if verdict.get("trust_score", 0) >= 0.6
            else None,
            "verified_by": "system",
            "ocr_data": ocr_data,
            "external_lookup": verify.get("matched_company"),
            "credit_code_valid": bool(cc_valid),
            "trust_score": verdict.get("trust_score"),
            "risk_level": verify.get("risk_level"),
            "lookup_provider": verify.get("lookup_provider"),
            "warnings": "; ".join(verdict.get("warnings", []) or []),
            "uploaded_by": agent_input.user_id,
        }
        try:
            from api.deps import get_supabase_admin
            supabase = get_supabase_admin()
            supabase.table("company_credentials").insert(record).execute()
        except Exception as e:
            logger.warning(f"failed to persist credential: {e}")

        # v6.0 EventBus — publish audit.recorded for compliance decision
        try:
            emit("audit.recorded", {
                "actor_id": agent_input.user_id,
                "action": "credential_review",
                "resource": "company_credentials",
                "before": None,
                "after": {
                    "trust_score": verdict.get("trust_score"),
                    "verdict": verdict.get("verdict"),
                },
            }, source="agent.compliance")
        except Exception as _e:
            logger.debug("eventbus publish failed: %s", _e)

        return AgentOutput(
            agent_name=self.name,
            text=(
                f"✅ 审核完成, 可信度: {verdict.get('trust_score', 0):.0%}\n"
                f"📋 {verdict.get('summary', '')}\n"
                f"⚠️ 待补充: {', '.join(verdict.get('missing_items', []) or []) or '无'}\n"
                f"🔎 OCR 通道: {ocr_provider}\n"
                f"🛰️ Lookup: {verify.get('lookup_provider')} (risk={verify.get('risk_level')})"
            ),
            artifacts={
                **verdict,
                "ocr_provider": ocr_provider,
                "ocr_text_snippet": ocr_text[:300],
                "lookup_provider": verify.get("lookup_provider"),
                "lookup_status": lookup_status,
                "credit_code_valid": cc_valid,
                "risk_level": verify.get("risk_level"),
                "warnings": verify.get("warnings"),
                "matched_company": verify.get("matched_company"),
                "expiry_alerts": verify.get("expiry_alerts", []),
            },
        )
