"""T6104 — Recommendation service (push talent to employer).

When a candidate↔role match succeeds we snapshot the candidate's full resume
+ contact info into a ``recommendations`` row and push an in-app notification
to the employer HR (the org that owns the role).

Lifecycle::

    pending ──view──▶ viewed ──accept──▶ accepted
                     │
                     └────reject──▶ rejected

Access contract (甲方合同):
    * employer (owns org_id) — sees the recommendation summary (score +
      reasons + skill gaps + risks) + the immutable resume snapshot +
      contact info for recommendations pushed to their org;
    * platform admin — everything, plus resume PDF download / export.

The service is DB-resilient: when Supabase is unreachable (dev without a
running stack) it keeps working against an in-memory store so the UI and
tests never break. Reads/writes against ``recommendations`` go through the
service-role admin client (RLS bypasses employer write restrictions).
"""
from __future__ import annotations

import logging
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("recruittech.services.recommendation")

VALID_STATUSES = ("pending", "viewed", "accepted", "rejected")
TERMINAL_STATUSES = ("accepted", "rejected")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Data contract
# ---------------------------------------------------------------------------

@dataclass
class Recommendation:
    """One pushed talent↔role recommendation."""

    id: str
    candidate_id: str
    role_id: str
    org_id: str
    match_score: int
    match_reasons: list[str] = field(default_factory=list)
    skill_gaps: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    resume_snapshot: dict[str, Any] = field(default_factory=dict)
    contact_info: dict[str, Any] = field(default_factory=dict)
    # denormalised display fields
    candidate_name: str = ""
    candidate_title: str = ""
    role_title: str = ""
    company_name: str = ""
    status: str = "pending"
    viewed_at: Optional[str] = None
    accepted_at: Optional[str] = None
    rejected_at: Optional[str] = None
    rejected_reason: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _row_to_rec(row: dict[str, Any]) -> Recommendation:
    """Map a Supabase row → Recommendation (tolerant of missing columns)."""
    return Recommendation(
        id=str(row.get("id")),
        candidate_id=str(row.get("candidate_id", "")),
        role_id=str(row.get("role_id", "")),
        org_id=str(row.get("org_id", "")),
        match_score=int(row.get("match_score") or 0),
        match_reasons=list(row.get("match_reasons") or []),
        skill_gaps=list(row.get("skill_gaps") or []),
        risks=list(row.get("risks") or []),
        resume_snapshot=dict(row.get("resume_snapshot") or {}),
        contact_info=dict(row.get("contact_info") or {}),
        candidate_name=str(row.get("candidate_name") or ""),
        candidate_title=str(row.get("candidate_title") or ""),
        role_title=str(row.get("role_title") or ""),
        company_name=str(row.get("company_name") or ""),
        status=str(row.get("status") or "pending"),
        viewed_at=row.get("viewed_at"),
        accepted_at=row.get("accepted_at"),
        rejected_at=row.get("rejected_at"),
        rejected_reason=row.get("rejected_reason"),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
    )


# ---------------------------------------------------------------------------
# Snapshot builder
# ---------------------------------------------------------------------------

def build_resume_snapshot(candidate: dict[str, Any]) -> dict[str, Any]:
    """Capture the immutable full resume at push time.

    ``candidate`` is the candidate row (or a TalentDetail dict) from the
    talent market. We copy the resume-relevant fields verbatim so the
    employer sees exactly what was matched.
    """
    return {
        "full_name": candidate.get("full_name") or candidate.get("name") or "",
        "title": candidate.get("title") or candidate.get("current_title") or "",
        "city": candidate.get("city") or candidate.get("location") or "",
        "skills": list(candidate.get("skills") or []),
        "seniority": candidate.get("seniority"),
        "education": candidate.get("education"),
        "experience_years": candidate.get("experience_years"),
        "availability": candidate.get("availability"),
        "salary_min_k": candidate.get("salary_min_k"),
        "salary_max_k": candidate.get("salary_max_k"),
        "summary": candidate.get("summary") or "",
        "industries": list(candidate.get("industries") or []),
        # v11.2 T6302 soft dimensions — captured so the immutable snapshot
        # preserves the identity-verification state + 五险一金/出差 signals
        # the employer actually saw at push time (R4 snapshot-completeness).
        "identity_status": candidate.get("identity_status"),
        "social_insurance_expectation": candidate.get(
            "social_insurance_expectation"
        ),
        "travel_tolerance": candidate.get("travel_tolerance"),
        "captured_at": _now_iso(),
    }


def build_contact_info(candidate: dict[str, Any]) -> dict[str, Any]:
    """Capture the contact info (PII) snapshot at push time."""
    return {
        "email": candidate.get("email"),
        "phone": candidate.get("phone"),
        "linkedin_url": candidate.get("linkedin_url"),
    }


# ---------------------------------------------------------------------------
# Match result normaliser
# ---------------------------------------------------------------------------

def _coerce_match_result(match_result: Any) -> dict[str, Any]:
    """Accept a dict, dataclass or object with score/reasons/gaps/risks."""
    if isinstance(match_result, dict):
        return dict(match_result)
    # dataclass / pydantic / namespace object
    keys = ("match_score", "score", "reasons", "match_reasons",
            "gaps", "skill_gaps", "risks")
    out: dict[str, Any] = {}
    for k in keys:
        if hasattr(match_result, k):
            out[k] = getattr(match_result, k)
    if hasattr(match_result, "model_dump"):
        try:
            out.update(match_result.model_dump())
        except Exception:  # noqa: BLE001
            pass
    return out


def _extract_score(match_result: dict[str, Any]) -> int:
    raw = match_result.get("match_score", match_result.get("score", 0))
    try:
        score = int(round(float(raw)))
    except (TypeError, ValueError):
        score = 0
    return max(0, min(100, score))


def _extract_list(match_result: dict[str, Any], *keys: str) -> list[str]:
    for k in keys:
        val = match_result.get(k)
        if val:
            return [str(v) for v in val]
    return []


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class RecommendationService:
    """CRUD + push notification over the ``recommendations`` table."""

    TABLE = "recommendations"

    def __init__(self, supabase: Any = None) -> None:
        # supabase admin client is optional — injected for tests, lazily
        # resolved from api.deps in production. A client that fails its first
        # round-trip is cached as None so the service degrades to an in-memory
        # store for the rest of its life (dev without a running DB).
        self._supabase = supabase
        self._probed = supabase is not None
        # in-memory fallback store keyed by id (dev/test only)
        self._mem: dict[str, Recommendation] = {}
        self._seq = 0

    # -- client resolution -------------------------------------------------

    def _sb(self):
        if self._probed:
            return self._supabase
        self._probed = True
        try:
            from api.deps import get_supabase_admin

            client = get_supabase_admin()
            # Probe once — a misconfigured/unreachable client (dev) is treated
            # the same as "no client at all" so we fall back to memory.
            client.table(self.TABLE).select("id").limit(1).execute()
            self._supabase = client
        except Exception as exc:  # pragma: no cover - dev fallback
            logger.info("recommendation: Supabase unavailable, using memory store: %s", exc)
            self._supabase = None
        return self._supabase

    # -- create ------------------------------------------------------------

    async def create_recommendation(
        self,
        *,
        candidate: dict[str, Any],
        role: dict[str, Any],
        match_result: Any,
        org_id: Optional[str] = None,
        notify: bool = True,
        hr_user_id: Optional[str] = None,
    ) -> Recommendation:
        """Create a recommendation record + push an in-app notice to the HR.

        ``candidate`` / ``role`` are the talent-market detail dicts (see
        :mod:`services.marketplace.talent_market`). ``match_result`` is the
        4-element match output (score + reasons + gaps + risks) produced by
        the v11.0 hard filter (T6105) — here we only read it, never recompute.
        """
        mr = _coerce_match_result(match_result)
        score = _extract_score(mr)
        reasons = _extract_list(mr, "match_reasons", "reasons")
        gaps = _extract_list(mr, "skill_gaps", "gaps")
        risks = _extract_list(mr, "risks")

        resume = build_resume_snapshot(candidate)
        contact = build_contact_info(candidate)

        # org_id: explicit arg → role → candidate → fallback
        org = (
            org_id
            or str(role.get("org_id") or role.get("organisation_id") or "")
            or str(candidate.get("org_id") or "")
        )

        payload = {
            "candidate_id": str(candidate.get("id") or ""),
            "role_id": str(role.get("id") or ""),
            "org_id": org,
            "match_score": score,
            "match_reasons": reasons,
            "skill_gaps": gaps,
            "risks": risks,
            "resume_snapshot": resume,
            "contact_info": contact,
            "candidate_name": resume.get("full_name") or str(candidate.get("name") or ""),
            "candidate_title": resume.get("title") or str(candidate.get("title") or ""),
            "role_title": str(role.get("title") or ""),
            "company_name": str(
                role.get("company") or role.get("company_name") or ""
            ),
            "status": "pending",
        }

        rec = await self._persist(payload)

        if notify:
            await self._push_hr_notification(
                rec=rec, hr_user_id=hr_user_id, score=score, reasons=reasons
            )
        return rec

    async def _persist(self, payload: dict[str, Any]) -> Recommendation:
        sb = self._sb()
        if sb is None:
            return self._persist_memory(payload)
        try:
            res = sb.table(self.TABLE).insert(payload).execute()
            row = (res.data or [{}])[0]
            return _row_to_rec(row)
        except Exception as exc:  # pragma: no cover - DB fallback
            logger.warning("recommendation insert failed, falling back to memory: %s", exc)
            return self._persist_memory(payload)

    def _persist_memory(self, payload: dict[str, Any]) -> Recommendation:
        self._seq += 1
        rec_id = str(self._seq)
        now = _now_iso()
        payload.setdefault("status", "pending")
        rec = Recommendation(
            id=rec_id,
            candidate_id=payload["candidate_id"],
            role_id=payload["role_id"],
            org_id=payload.get("org_id", ""),
            match_score=payload["match_score"],
            match_reasons=payload["match_reasons"],
            skill_gaps=payload["skill_gaps"],
            risks=payload["risks"],
            resume_snapshot=payload["resume_snapshot"],
            contact_info=payload["contact_info"],
            candidate_name=payload.get("candidate_name", ""),
            candidate_title=payload.get("candidate_title", ""),
            role_title=payload.get("role_title", ""),
            company_name=payload.get("company_name", ""),
            status=payload["status"],
            created_at=now,
            updated_at=now,
        )
        self._mem[rec_id] = rec
        return rec

    # -- read --------------------------------------------------------------

    async def list_for_org(
        self,
        *,
        org_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Recommendation]:
        sb = self._sb()
        if sb is None:
            org_recs = [r for r in self._mem.values() if r.org_id == org_id]
            if not org_recs:
                # dev fallback: seed a small demo catalog the first time an
                # empty org is queried so the UI is never blank.
                org_recs = _seed_demo_recommendations(self, org_id)
            recs = org_recs
            if status:
                recs = [r for r in recs if r.status == status]
            recs = sorted(recs, key=lambda r: r.created_at, reverse=True)
            return recs[offset : offset + limit]
        try:
            q = (
                sb.table(self.TABLE)
                .select("*")
                .eq("org_id", org_id)
                .order("created_at", desc=True)
                .range(offset, offset + limit - 1)
            )
            if status:
                q = q.eq("status", status)
            res = q.execute()
            return [_row_to_rec(r) for r in (res.data or [])]
        except Exception as exc:  # pragma: no cover - DB fallback
            logger.warning("recommendation list failed: %s", exc)
            return []

    async def get(self, rec_id: str) -> Optional[Recommendation]:
        sb = self._sb()
        if sb is None:
            return self._mem.get(rec_id)
        try:
            res = (
                sb.table(self.TABLE)
                .select("*")
                .eq("id", rec_id)
                .limit(1)
                .execute()
            )
            rows = res.data or []
            return _row_to_rec(rows[0]) if rows else None
        except Exception as exc:  # pragma: no cover - DB fallback
            logger.warning("recommendation get failed: %s", exc)
            return self._mem.get(rec_id)

    # -- status transitions -----------------------------------------------

    async def mark_viewed(self, rec_id: str) -> Optional[Recommendation]:
        return await self._update_status(rec_id, "viewed")

    async def accept(self, rec_id: str) -> Optional[Recommendation]:
        return await self._update_status(rec_id, "accepted")

    async def reject(
        self, rec_id: str, reason: Optional[str] = None
    ) -> Optional[Recommendation]:
        return await self._update_status(rec_id, "rejected", reason=reason)

    async def _update_status(
        self,
        rec_id: str,
        status: str,
        *,
        reason: Optional[str] = None,
    ) -> Optional[Recommendation]:
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid recommendation status: {status}")

        now = _now_iso()
        patch: dict[str, Any] = {"status": status, "updated_at": now}
        if status == "viewed":
            patch["viewed_at"] = now
        elif status == "accepted":
            patch["accepted_at"] = now
        elif status == "rejected":
            patch["rejected_at"] = now
            if reason is not None:
                patch["rejected_reason"] = reason

        sb = self._sb()
        if sb is None:
            return self._update_memory(rec_id, patch)
        try:
            res = (
                sb.table(self.TABLE)
                .update(patch)
                .eq("id", rec_id)
                .execute()
            )
            rows = res.data or []
            return _row_to_rec(rows[0]) if rows else None
        except Exception as exc:  # pragma: no cover - DB fallback
            logger.warning("recommendation update failed: %s", exc)
            return self._update_memory(rec_id, patch)

    def _update_memory(
        self, rec_id: str, patch: dict[str, Any]
    ) -> Optional[Recommendation]:
        rec = self._mem.get(rec_id)
        if rec is None:
            return None
        for k, v in patch.items():
            setattr(rec, k, v)
        rec.updated_at = _now_iso()
        return rec

    # -- download / export (admin only — enforced at API layer) ------------

    async def render_resume_text(self, rec_id: str) -> Optional[str]:
        """Plain-text render of the snapshot resume (for PDF/preview).

        Returns None when the recommendation does not exist.
        """
        rec = await self.get(rec_id)
        if rec is None:
            return None
        s = rec.resume_snapshot
        lines: list[str] = []
        title = s.get("title") or rec.candidate_title or "候选人"
        lines.append(f"{s.get('full_name') or rec.candidate_name or '匿名候选人'} — {title}")
        meta: list[str] = []
        if s.get("city"):
            meta.append(f"城市: {s['city']}")
        if s.get("seniority"):
            meta.append(f"职级: {s['seniority']}")
        if s.get("education"):
            meta.append(f"学历: {s['education']}")
        if s.get("experience_years") is not None:
            meta.append(f"经验: {s['experience_years']}年")
        if s.get("availability"):
            meta.append(f"状态: {s['availability']}")
        # v11.2 identity-verification label in the snapshot (R4 completeness).
        ident = s.get("identity_status")
        if ident:
            _ident_labels = {
                "pending": "待上传",
                "submitted": "待审核",
                "verified": "已认证",
            }
            meta.append(
                f"身份: {_ident_labels.get(ident, ident)}"
            )
        if meta:
            lines.append(" · ".join(meta))
        if s.get("skills"):
            lines.append("技能: " + ", ".join(s["skills"]))
        if s.get("summary"):
            lines.append("")
            lines.append(str(s["summary"]))
        lines.append("")
        lines.append(f"匹配分数: {rec.match_score}/100")
        if rec.match_reasons:
            lines.append("匹配理由: " + "; ".join(rec.match_reasons))
        if rec.skill_gaps:
            lines.append("能力缺口: " + "; ".join(rec.skill_gaps))
        if rec.risks:
            lines.append("风险提示: " + "; ".join(rec.risks))
        contact = rec.contact_info or {}
        contact_bits = [
            v for v in (contact.get("email"), contact.get("phone"),
                        contact.get("linkedin_url")) if v
        ]
        if contact_bits:
            lines.append("")
            lines.append("联系方式: " + " | ".join(contact_bits))
        return "\n".join(lines)

    # -- communication channels (T6304) -----------------------------------

    CHANNELS_TABLE = "communication_channels"

    async def initiate_contact(
        self,
        *,
        candidate_id: str,
        role_id: str,
        org_id: str,
        match_score: Optional[int] = None,
        initiated_by: str = "employer",
    ) -> dict[str, Any]:
        """Open a communication channel for a recommended candidate↔role pair.

        Reuses the ``communication_channels`` table (T6302 migration). The
        threshold gate itself is enforced upstream by the talent-market
        service (:func:`initiate_contact`), which calls this helper to persist
        the channel once the score check passes. Returns the channel row as a
        dict. Falls back to an in-memory dict when Supabase is unreachable so
        tests/UI never break.
        """
        score = int(match_score) if match_score is not None else 0
        payload = {
            "candidate_id": str(candidate_id),
            "role_id": str(role_id),
            "org_id": str(org_id),
            "initiated_by": initiated_by,
            "match_score": score,
            "status": "open",
        }
        sb = self._sb()
        if sb is not None:
            try:
                res = sb.table(self.CHANNELS_TABLE).upsert(
                    payload, on_conflict="candidate_id,role_id"
                ).execute()
                row = (res.data or [{}])[0]
                return dict(row)
            except Exception as exc:  # pragma: no cover - DB fallback
                logger.warning("recommendation channel upsert failed: %s", exc)
        # in-memory fallback
        return await self._channel_memory(payload)

    async def _channel_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        """In-memory channel store (dev/test resilience)."""
        store: dict[tuple[str, str], dict[str, Any]] = self.__dict__.setdefault(
            "_channels_mem", {}
        )
        key = (payload["candidate_id"], payload["role_id"])
        now = _now_iso()
        existing = store.get(key)
        if existing:
            existing.update(payload)
            existing["updated_at"] = now
            return existing
        self._seq += 1
        row = {
            "id": f"rec_ch_{self._seq}",
            **payload,
            "created_at": now,
            "updated_at": now,
        }
        store[key] = row
        return row

    async def list_channels(
        self,
        *,
        org_id: Optional[str] = None,
        candidate_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """List communication channels for an org or candidate."""
        sb = self._sb()
        if sb is not None:
            try:
                q = (
                    sb.table(self.CHANNELS_TABLE)
                    .select("*")
                    .eq("status", "open")
                )
                if org_id:
                    q = q.eq("org_id", org_id)
                if candidate_id:
                    q = q.eq("candidate_id", candidate_id)
                res = q.order("created_at", desc=True).execute()
                return [dict(r) for r in (res.data or [])]
            except Exception as exc:  # pragma: no cover - DB fallback
                logger.warning("recommendation channel list failed: %s", exc)
        store: dict[tuple[str, str], dict[str, Any]] = self.__dict__.get(
            "_channels_mem", {}
        )
        rows = list(store.values())
        if org_id:
            rows = [r for r in rows if r.get("org_id") == org_id]
        if candidate_id:
            rows = [r for r in rows if r.get("candidate_id") == candidate_id]
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows

    # -- push notification -------------------------------------------------

    async def _push_hr_notification(
        self,
        *,
        rec: Recommendation,
        hr_user_id: Optional[str],
        score: int,
        reasons: list[str],
    ) -> bool:
        """Reuse the v6.0 notify dispatcher to push an in-app notice to the HR.

        Falls through silently if the dispatcher is unavailable so the
        recommendation still gets created.
        """
        target = hr_user_id or rec.org_id  # org-scoped broadcast when no HR id
        title = f"新推荐: {rec.candidate_name or '候选人'} → {rec.role_title or '岗位'}"
        reason_text = "；".join(reasons[:2]) if reasons else "综合画像匹配"
        content = (
            f"匹配分数 {score}/100。{reason_text}。"
            f"前往推荐中心查看完整简历与联系方式。"
        )
        payload = {
            "type": "talent_recommendation",
            "recommendation_id": rec.id,
            "candidate_id": rec.candidate_id,
            "role_id": rec.role_id,
            "org_id": rec.org_id,
            "match_score": score,
        }
        try:
            # v6.0 notify dispatcher entrypoint. ``services.notify`` is the
            # package that re-exports ``dispatch`` (the standalone
            # services/notify.py shim is shadowed by the package dir).
            from services.notify import dispatch

            return await dispatch(
                channel="in_app",
                user_id=str(target),
                title=title,
                content=content,
                payload=payload,
            )
        except Exception as exc:  # pragma: no cover - dispatcher optional
            logger.info("recommendation notify skipped: %s", exc)
            return False


# ---------------------------------------------------------------------------
# Singleton + factory
# ---------------------------------------------------------------------------

_service_singleton: Optional[RecommendationService] = None


def get_service() -> RecommendationService:
    global _service_singleton
    if _service_singleton is None:
        _service_singleton = RecommendationService()
    return _service_singleton


def reset_service(supabase: Any = None) -> RecommendationService:
    """Test helper: replace the singleton (optionally with a fake client)."""
    global _service_singleton
    _service_singleton = RecommendationService(supabase=supabase)
    return _service_singleton


# ---------------------------------------------------------------------------
# Dev helpers — synthetic recommendation catalog (mirror of talent_market)
# ---------------------------------------------------------------------------

def _seed_demo_recommendations(
    svc: RecommendationService, org_id: str, n: int = 6
) -> list[Recommendation]:
    """Populate the memory store with a few demo recommendations (dev only).

    Only used when there is no DB and the list for an org is empty. Builds the
    Recommendation rows directly (sync) rather than going through the async
    ``create_recommendation`` path so it is safe to call from inside an
    awaited coroutine.
    """
    rng = random.Random(hash(org_id) & 0xFFFFFFFF)
    names = ["张伟", "李娜", "王强", "刘洋", "陈静", "赵磊"]
    titles = ["后端工程师", "算法工程师", "全栈工程师", "DevOps 工程师"]
    roles = ["资深后端工程师", "机器学习工程师", "技术专家"]
    out: list[Recommendation] = []
    statuses = ["pending", "pending", "viewed", "accepted", "rejected"]
    for i in range(n):
        name = names[i % len(names)]
        title = rng.choice(titles)
        role_title = rng.choice(roles)
        skills = rng.sample(
            ["Python", "Go", "Kubernetes", "Redis", "Kafka", "PyTorch", "LLM"],
            rng.randint(3, 5),
        )
        svc._seq += 1
        rec_id = str(svc._seq)
        now = _now_iso()
        status = rng.choice(statuses)
        rec = Recommendation(
            id=rec_id,
            candidate_id=f"demo_talent_{i}",
            role_id=f"demo_role_{i}",
            org_id=org_id,
            match_score=rng.randint(70, 96),
            match_reasons=[
                f"技能匹配 {rng.randint(3,5)}/5",
                rng.choice(["同城", "职级契合", "薪资匹配"]),
            ],
            skill_gaps=rng.sample(
                ["缺 K8s 经验", "缺分布式经验", "缺团队管理经验"],
                rng.randint(0, 2),
            ),
            risks=rng.sample(
                ["到岗不确定", "薪资偏高", "竞业限制"],
                rng.randint(0, 1),
            ),
            resume_snapshot={
                "full_name": name,
                "title": title,
                "city": rng.choice(["北京", "上海", "深圳", "杭州"]),
                "skills": skills,
                "seniority": rng.choice(["中级", "高级", "资深"]),
                "education": rng.choice(["本科", "硕士"]),
                "experience_years": rng.randint(2, 10),
                "availability": rng.choice(["在职看机会", "离职可立即上岗"]),
                "summary": f"{name}，{title}，专注 {', '.join(skills[:2])}。",
                "captured_at": now,
            },
            contact_info={
                "email": f"talent{i}@example.com",
                "phone": f"1{rng.choice([3,5,8])}{rng.randint(100000000,999999999)}",
                "linkedin_url": f"https://linkedin.com/in/talent{i}",
            },
            candidate_name=name,
            candidate_title=title,
            role_title=role_title,
            company_name="演示企业",
            status=status,
            viewed_at=now if status in ("viewed", "accepted", "rejected") else None,
            accepted_at=now if status == "accepted" else None,
            rejected_at=now if status == "rejected" else None,
            created_at=now,
            updated_at=now,
        )
        svc._mem[rec_id] = rec
        out.append(rec)
    return out
