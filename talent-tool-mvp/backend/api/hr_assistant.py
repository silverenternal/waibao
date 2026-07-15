"""T6108 — HR Assistant API (resume compare + report + interview questions).

Mounted under ``/api/hr-assistant``:

* ``POST /api/hr-assistant/compare``               — resume side-by-side compare
* ``POST /api/hr-assistant/interview-questions``   — interview question template
* ``GET  /api/hr-assistant/compare/{id}/export``   — export a saved compare report

The compare endpoint reuses the T2301 ``ComparisonService`` over the
``candidates`` table (5-dimension alignment + top-3 diff highlights) and
renders a candidate-centric matrix the HR can read at a glance. The
interview-questions endpoint draws from the T1301 static question bank
(100 questions × 10 role categories) and shapes 5-10 into an interview
template. Exports reuse the T2303 ``DocumentGenerator`` (docx/pdf/txt).

Access: authenticated ``client`` (employer) or ``admin``.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user, require_role
from api.deps import get_supabase
from contracts.shared import UserRole
from services.matching.comparison import ComparisonService
from services.platform.document_generator import DocumentGenerator

logger = logging.getLogger("recruittech.api.hr_assistant")
router = APIRouter(prefix="/api/hr-assistant", tags=["hr-assistant"])


_generator: DocumentGenerator | None = None


def _get_generator() -> DocumentGenerator:
    global _generator
    if _generator is None:
        _generator = DocumentGenerator()
    return _generator


# ---------------------------------------------------------------------------
# request / response schemas
# ---------------------------------------------------------------------------

class CompareRequest(BaseModel):
    candidate_ids: list[str] = Field(..., min_length=2, max_length=5)
    role_id: Optional[str] = Field(None, description="可选: 对比的 role context")
    title: Optional[str] = None


class InterviewQuestionsRequest(BaseModel):
    role: str = Field(..., min_length=1, description="岗位 category, e.g. backend_engineer")
    count: int = Field(10, ge=1, le=20)
    difficulty: Optional[str] = Field(
        None, description="可选难度: junior/mid/senior/lead"
    )
    title: Optional[str] = None


# ---------------------------------------------------------------------------
# resume compare
# ---------------------------------------------------------------------------

@router.post("/compare")
async def compare_resumes(
    req: CompareRequest,
    user: CurrentUser = Depends(require_role(UserRole.client, UserRole.admin)),
    supabase=Depends(get_supabase),
):
    """简历并排比较 (2-5 份).

    返回 5 维度对齐矩阵 (基本信息/技能/学历/经验/匹配度) + top-3 差异高亮.
    复用 T2301 ComparisonService.
    """
    raw_ids = [s.strip() for s in req.candidate_ids if s and s.strip()]
    if len(raw_ids) < 2:
        raise HTTPException(status_code=400, detail="至少需要 2 份简历")
    if len(raw_ids) > 5:
        raise HTTPException(status_code=400, detail="最多 5 份简历")

    try:
        candidate_ids = [UUID(s) for s in raw_ids]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"无效候选人 ID: {e}")

    role_id: Optional[UUID] = None
    if req.role_id:
        try:
            role_id = UUID(req.role_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"无效 role_id: {e}")

    service = ComparisonService(supabase)
    try:
        result = await service.compare_candidates(candidate_ids, role_id=role_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("hr_assistant.compare failed")
        raise HTTPException(status_code=500, detail=str(e))

    payload = result.to_dict()
    payload["title"] = req.title or f"简历对比 ({len(candidate_ids)} 人)"
    payload["export_path"] = "/api/hr-assistant/compare/0/export"
    return payload


# ---------------------------------------------------------------------------
# interview question template
# ---------------------------------------------------------------------------

@router.post("/interview-questions")
async def interview_questions(
    req: InterviewQuestionsRequest,
    user: CurrentUser = Depends(require_role(UserRole.client, UserRole.admin)),
):
    """面试题模板: 从 question_bank 按岗位生成 5-10 题.

    复用 T1301 静态题库 (100 题 × 10 类). 每题含 prompt / 期望要点 /
    考察技能 / 难度 / 类型 / 建议时长 / 评分权重.
    """
    if req.difficulty and req.difficulty not in ("junior", "mid", "senior", "lead"):
        raise HTTPException(
            status_code=400,
            detail="difficulty 必须是 junior/mid/senior/lead 之一",
        )
    try:
        from services.jobseeker.question_bank import question_bank
    except Exception as e:  # pragma: no cover - defensive
        logger.exception("question_bank import failed")
        raise HTTPException(status_code=500, detail=f"题库不可用: {e}")

    try:
        questions = question_bank.select_questions(
            role=req.role,
            count=req.count,
            difficulty=req.difficulty,
        )
    except Exception as e:
        logger.exception("question_bank.select_questions failed")
        raise HTTPException(status_code=500, detail=str(e))

    total_duration = sum(q.duration_sec for q in questions)
    return {
        "role": req.role,
        "title": req.title or f"{req.role} 面试题模板",
        "count": len(questions),
        "difficulty": req.difficulty,
        "estimated_minutes": round(total_duration / 60, 1),
        "questions": [
            {
                "id": q.id,
                "title": q.title,
                "prompt": q.prompt,
                "expected_points": q.expected_points,
                "skills": q.skills,
                "difficulty": q.difficulty,
                "type": q.type,
                "duration_sec": q.duration_sec,
                "weights": q.weights,
            }
            for q in questions
        ],
    }


# ---------------------------------------------------------------------------
# compare report export
# ---------------------------------------------------------------------------

def _render_compare_text(data: dict[str, Any], title: str) -> bytes:
    """Render a compare report as UTF-8 text (always-available fallback)."""
    lines: list[str] = [title, "=" * 40, ""]
    items = data.get("items") or data.get("candidates") or []
    for item in items:
        name = item.get("name") or item.get("id")
        lines.append(f"- {name}")
        dims = item.get("dimensions") or {}
        for dim_name, dim_val in dims.items():
            if isinstance(dim_val, dict):
                score = dim_val.get("score")
                detail = dim_val.get("detail") or dim_val.get("label") or ""
                lines.append(f"    {dim_name}: {score} {detail}")
            else:
                lines.append(f"    {dim_name}: {dim_val}")
        lines.append("")
    highlights = data.get("highlights") or []
    if highlights:
        lines.append("差异高亮 (Top 3):")
        for h in highlights[:3]:
            dim = h.get("dimension") or h.get("name") or ""
            spread = h.get("spread")
            lines.append(f"  · {dim} (spread={spread})")
        lines.append("")
    lines.append(
        f"导出时间: {data.get('exported_at', '')} — HR Assistant (T6108)"
    )
    return "\n".join(lines).encode("utf-8")


@router.get("/compare/{compare_id}/export")
async def export_compare_report(
    compare_id: str,
    format: str = Query("txt", pattern="^(txt|docx|pdf)$"),
    user: CurrentUser = Depends(require_role(UserRole.client, UserRole.admin)),
    supabase=Depends(get_supabase),
):
    """导出简历对比报告 (PDF/Word/txt).

    目前以文本/docx/pdf 形式渲染一份对比快照; compare_id 用于未来持久化
    已保存的对比快照 (复用 match/compare/saved). 当 compare_id 为 '0' 或
    未持久化时, 返回一份示例对比报告骨架供 HR 调整格式.
    """
    # 1) 尝试从已保存的对比快照恢复 payload (T2301 match/compare/saved)
    data: Optional[dict[str, Any]] = None
    if compare_id and compare_id != "0":
        try:
            res = (
                supabase.table("compare_snapshots")
                .select("payload,title")
                .eq("id", compare_id)
                .limit(1)
                .execute()
            )
            if res.data:
                row = res.data[0]
                data = row.get("payload") or {}
                if not isinstance(data, dict):
                    data = {"items": data}
                data["title"] = data.get("title") or row.get("title")
        except Exception as exc:  # table may not exist yet
            logger.info("compare export: snapshot lookup skipped: %s", exc)

    if data is None:
        data = {
            "title": "简历对比报告 (示例)",
            "items": [],
            "highlights": [],
        }

    title = data.get("title") or "简历对比报告"

    if format == "txt":
        data["exported_at"] = _now_cn()
        content = _render_compare_text(data, title)
        return Response(
            content=content,
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="compare_report.txt"'
                ),
            },
        )

    # docx / pdf — reuse DocumentGenerator's candidate_report renderer with
    # the compare matrix folded into the data dict.
    gen = _get_generator()
    try:
        result = gen.generate(
            template="candidate_report",
            fmt=format,
            data=data,
            title=title,
        )
    except Exception as exc:
        logger.warning("compare export docgen failed, fallback to txt: %s", exc)
        content = _render_compare_text(data, title)
        return Response(
            content=content,
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="compare_report.txt"'
                ),
            },
        )
    return Response(
        content=result.content,
        media_type=result.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"',
        },
    )


def _now_cn() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
