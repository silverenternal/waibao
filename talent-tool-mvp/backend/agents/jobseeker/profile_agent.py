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
from agents.prompts import get_prompt as _get_prompt
from agents.toolkit import llm_call
from eventbus import emit

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

    async def _maybe_analyze_video_resume(self, ctx: dict[str, Any]) -> dict[str, Any] | None:
        """T2203: 如果 ctx 带 video_url,调用 video_resume_analyzer.

        返回 VideoResumeAnalysis.to_dict();失败返回 {"_error": ...}.
        """
        video_url = ctx.get("video_url") or ctx.get("video_resume_url")
        if not video_url:
            return None
        try:
            from services.jobseeker.video_resume_analyzer import analyze_video_resume
            analysis = await analyze_video_resume(
                video_url,
                interval_sec=float(ctx.get("video_interval_sec", 5.0)),
                max_frames=int(ctx.get("video_max_frames", 6)),
                transcript_excerpt=str(ctx.get("video_transcript", "")),
                blob_size_bytes=ctx.get("video_size_bytes"),
            )
            return analysis.to_dict()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"profile_agent video resume analysis failed: {e}")
            return {"_error": str(e), "source_url": video_url}

    def _merge_video_into_profile(self, profile: dict, analysis_dict: dict) -> dict:
        """T2203: 把视频简历分析合并进 profile.

        使用 video_resume_analyzer.merge_video_into_profile;权重 0.15 (视频) / 0.85 (文本).
        """
        try:
            from services.jobseeker.video_resume_analyzer import (
                VideoResumeAnalysis,
                VideoResumeScores,
                NonVerbalSignals,
                merge_video_into_profile,
            )
            scores_dict = analysis_dict.get("scores") or {}
            scores = VideoResumeScores(**{k: float(v) for k, v in scores_dict.items() if k != "overall"})
            scores.overall = float(scores_dict.get("overall", 0.0))
            nv = analysis_dict.get("non_verbal") or {}
            non_verbal = NonVerbalSignals(
                expression=str(nv.get("expression", "")),
                eye_contact=str(nv.get("eye_contact", "")),
                body_language=str(nv.get("body_language", "")),
                notes=list(nv.get("notes") or []),
            )
            analysis = VideoResumeAnalysis(
                source_url=analysis_dict.get("source_url", ""),
                video_metadata=analysis_dict.get("video_metadata", {}),
                frames_analyzed=int(analysis_dict.get("frames_analyzed", 0)),
                scores=scores,
                non_verbal=non_verbal,
                strengths=list(analysis_dict.get("strengths") or []),
                suggestions=list(analysis_dict.get("suggestions") or []),
                transcript_excerpt=str(analysis_dict.get("transcript_excerpt", "")),
                tags=list(analysis_dict.get("tags") or []),
                confidence=float(analysis_dict.get("confidence", 0.0)),
                model=str(analysis_dict.get("model", "")),
                provider_chain=list(analysis_dict.get("provider_chain") or []),
                analyzed_at=str(analysis_dict.get("analyzed_at", "")),
            )
            return merge_video_into_profile(profile, analysis)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"_merge_video_into_profile failed: {e}")
            return profile

    def _merge_resume_into_profile(self, profile: dict, parsed: dict) -> dict:
        """把 LLM 抽取出的 resume 字段 merge 进 profile。

        字段合并策略:
        - basic.* (name/email/phone/location): 只在 profile 已有字段为空时填入
        - education / experience / certifications / portfolio / interests: 同名 list 合并去重
        - skills: 按 name 去重,合并 years / level (取最大值)
        - highlights: 仅在 profile 无 highlights 时填入
        - provenance: 始终记录 (source_url / raw_text_snippet / provider_chain / last_ocr_at)
        """
        extracted = parsed.get("extracted") or {}
        basic = extracted.get("basic") if isinstance(extracted.get("basic"), dict) else {}
        merged = dict(profile)

        # ---- 1. basic fields ----
        if basic:
            name = basic.get("name") if isinstance(basic.get("name"), str) else None
            if name and not merged.get("name"):
                merged["name"] = name
            for k in ("email", "phone", "location"):
                v = basic.get(k)
                if v and not merged.get(k):
                    merged[k] = v

        # ---- 2. education (按 school+degree 去重) ----
        edu = extracted.get("education") or []
        if edu:
            existing_edu = merged.get("education") or []
            seen = {
                (e.get("school"), e.get("degree")) for e in existing_edu if isinstance(e, dict)
            }
            for e in edu:
                if isinstance(e, dict) and (e.get("school"), e.get("degree")) not in seen:
                    existing_edu.append(e)
                    seen.add((e.get("school"), e.get("degree")))
            merged["education"] = existing_edu

        # ---- 3. experience (按 company+title 去重) ----
        exp = extracted.get("experience") or []
        if exp:
            existing_exp = merged.get("experience") or []
            seen = {
                (e.get("company"), e.get("title")) for e in existing_exp if isinstance(e, dict)
            }
            for e in exp:
                if isinstance(e, dict) and (e.get("company"), e.get("title")) not in seen:
                    existing_exp.append(e)
                    seen.add((e.get("company"), e.get("title")))
            merged["experience"] = existing_exp

        # ---- 4. skills (按 name 去重, level/years 取 max) ----
        skills = extracted.get("skills") or []
        if skills:
            existing_skills = {
                s.get("name"): dict(s) for s in (merged.get("skills") or []) if isinstance(s, dict)
            }
            for s in skills:
                if not isinstance(s, dict) or not s.get("name"):
                    continue
                name = s["name"]
                if name in existing_skills:
                    # 取更长的 years / 更高的 level
                    cur = existing_skills[name]
                    try:
                        if int(s.get("years", 0)) > int(cur.get("years", 0)):
                            cur["years"] = s["years"]
                    except (ValueError, TypeError):
                        pass
                    if s.get("level") and not cur.get("level"):
                        cur["level"] = s["level"]
                    existing_skills[name] = cur
                else:
                    existing_skills[name] = s
            merged["skills"] = list(existing_skills.values())

        # ---- 5. certifications / portfolio / interests / highlights (merge unique) ----
        for list_key in ("certifications", "portfolio", "interests", "highlights"):
            items = extracted.get(list_key) or []
            if not items:
                continue
            existing_items = merged.get(list_key) or []
            if not isinstance(existing_items, list):
                existing_items = [existing_items]
            seen_keys = set()
            for it in existing_items:
                if isinstance(it, dict):
                    seen_keys.add(it.get("name") or it.get("title") or it.get("fact") or str(it))
                else:
                    seen_keys.add(str(it))
            for it in items:
                key = (it.get("name") or it.get("title") or it.get("fact") or str(it)) if isinstance(it, dict) else str(it)
                if key not in seen_keys:
                    existing_items.append(it)
                    seen_keys.add(key)
            merged[list_key] = existing_items

        # ---- 6. overall_impression → summary ----
        impression = extracted.get("overall_impression")
        if impression and not merged.get("summary"):
            merged["summary"] = impression

        # ---- 7. provenance ----
        import datetime as _dt
        merged["_resume_source_url"] = parsed.get("source_url")
        merged["_resume_raw_text_snippet"] = (parsed.get("raw_text") or "")[:300]
        merged["_resume_provider_chain"] = parsed.get("provider_chain", [])
        merged["_resume_ocr_provider"] = parsed.get("ocr_provider")
        merged["_resume_last_parsed_at"] = _dt.datetime.utcnow().isoformat() + "Z"
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

        # ---- T2203 视频简历理解 ----
        video_analysis = await self._maybe_analyze_video_resume(ctx)
        if video_analysis and "_error" not in video_analysis:
            existing = self._merge_video_into_profile(existing, video_analysis)
        video_notice = ""
        if video_analysis and "_error" in video_analysis:
            video_notice = f"\n(注:视频简历分析失败 — {video_analysis.get('_error', '未知错误')})"

        system = _get_prompt("profile_agent", "system", default=PROFILE_INTAKE_PROMPT)
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
        if video_analysis and "_error" not in video_analysis:
            try:
                scores = video_analysis.get("scores") or {}
                overall = int(float(scores.get("overall", 0)) * 100)
                warm = f"我看了你的视频简历(综合 {overall} 分)。{warm}"
            except Exception:  # noqa: BLE001
                pass

        # v6.0 EventBus — publish profile.updated + profile.enriched (when resume parsed)
        try:
            emit("profile.updated", {
                "user_id": agent_input.user_id,
                "candidate_id": ctx.get("candidate_id"),
                "fields": [k for k in (updated.keys() if isinstance(updated, dict) else [])][:10],
                "completeness": result.get("completion", 0.5),
                "source": "profile_agent",
            }, source="agent.profile")
            if resume_parsed and "_error" not in resume_parsed:
                emit("profile.enriched", {
                    "user_id": agent_input.user_id,
                    "candidate_id": ctx.get("candidate_id"),
                    "new_skills": (resume_parsed.get("skills") or [])[:10],
                    "source": "resume_parser",
                }, source="agent.profile")
        except Exception as _e:
            logger.debug("eventbus publish failed: %s", _e)

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
                "video_resume_analyzed": bool(video_analysis and "_error" not in video_analysis),
                "video_resume_scores": (video_analysis or {}).get("scores"),
            },
            memory_writes=[{
                "scope": "long_term",
                "key": "profile",
                "value": updated,
            }],
        )


def build_relationship_aware_greeting(
    user_id: str,
    *,
    name: str = "",
) -> dict[str, Any]:
    """v8.1 T3601 — 关系上下文感知的欢迎语.

    返回:
        {
          "greeting": "...",
          "tone": "friendly|casual|gentle|formal|celebratory",
          "avatar": "wave|smile|heart|briefcase|tada",
          "stage": "new_user|active_job_seeker|on_break|negotiating|hired"
        }
    """
    try:
        from services.jobseeker.relationship import (
            get_relationship_service,
            STAGE_TONE,
        )
    except Exception:  # pragma: no cover
        return {
            "greeting": f"你好 {name or '同学'}!",
            "tone": "friendly",
            "avatar": "wave",
            "stage": "new_user",
        }

    rel = get_relationship_service()
    rel.touch_interaction(user_id)
    stage = rel.get_stage(user_id)
    tone = STAGE_TONE.get(stage, STAGE_TONE["new_user"])
    greeting = tone["greeting_template"].format(name=name or "同学")
    return {
        "greeting": greeting,
        "tone": tone["tone"],
        "avatar": tone["avatar"],
        "stage": stage,
    }
