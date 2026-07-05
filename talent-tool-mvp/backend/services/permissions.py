"""多角色鉴权 + RBAC.

支持 5 种 persona:
- jobseeker (求职者)
- boss (老板)
- hr (HR)
- dept_head (部门负责人)
- admin (管理员)

一人可多 persona(通过 user_personas 关联表).
"""
from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException
from supabase import Client

from api.auth import CurrentUser, get_current_user


class Persona(str, Enum):
    jobseeker = "jobseeker"
    boss = "boss"
    hr = "hr"
    dept_head = "dept_head"
    admin = "admin"


# persona → 可访问的模块
PERSONA_ACCESS = {
    Persona.jobseeker: ["profile", "journal", "plan", "policy_browse", "match_view"],
    Persona.boss: ["vision", "talent_brief", "multilogue", "hr_overview", "match_view"],
    Persona.hr: ["compliance", "policy", "talent_brief", "job_spec", "multilogue",
                 "candidate_pool", "match_view", "hr_service", "vision"],
    Persona.dept_head: ["job_spec", "talent_brief", "multilogue", "candidate_pool"],
    Persona.admin: ["*"],   # 全部
}


class PersonaUser:
    """扩展 CurrentUser,带多个 persona."""

    def __init__(self, user_id: UUID, email: str, primary_persona: Persona,
                 personas: list[Persona], organisation_id: Optional[UUID] = None):
        self.id = user_id
        self.email = email
        self.primary_persona = primary_persona
        self.personas = personas
        self.organisation_id = organisation_id

    def has_persona(self, p: Persona) -> bool:
        return p in self.personas

    def can_access(self, module: str) -> bool:
        for p in self.personas:
            allowed = PERSONA_ACCESS.get(p, [])
            if "*" in allowed or module in allowed:
                return True
        return False


async def get_persona_user(
    user: CurrentUser = Depends(get_current_user),
) -> PersonaUser:
    """根据 JWT + user_personas 表获取完整 persona 信息."""
    from api.deps import get_supabase_admin
    supabase = get_supabase_admin()

    # 1. 读取 user_personas 表
    result = supabase.table("user_personas").select("*").eq(
        "user_id", str(user.id)
    ).execute()

    if result.data:
        personas = [Persona(p["persona"]) for p in result.data]
        primary = Persona(result.data[0]["persona"])
        org_id = result.data[0].get("organisation_id")
    else:
        # fallback: 从 JWT 的 role 推断
        try:
            primary = Persona(user.role.value)
        except ValueError:
            primary = Persona.jobseeker
        personas = [primary]
        org_id = None

    return PersonaUser(
        user_id=user.id,
        email=user.email,
        primary_persona=primary,
        personas=personas,
        organisation_id=UUID(org_id) if org_id else None,
    )


def require_persona(*required: Persona):
    """依赖工厂: 要求当前用户拥有任一指定 persona."""

    async def _check(u: PersonaUser = Depends(get_persona_user)) -> PersonaUser:
        if not any(u.has_persona(p) for p in required):
            raise HTTPException(
                status_code=403,
                detail=f"Required persona: {', '.join(p.value for p in required)}",
            )
        return u

    return _check


def require_module(module: str):
    """依赖工厂: 要求当前用户能访问指定模块."""

    async def _check(u: PersonaUser = Depends(get_persona_user)) -> PersonaUser:
        if not u.can_access(module):
            raise HTTPException(
                status_code=403,
                detail=f"Module '{module}' not accessible",
            )
        return u

    return _check