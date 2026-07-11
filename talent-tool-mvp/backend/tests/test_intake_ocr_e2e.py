"""T702 — Resume OCR end-to-end (1.1 强化).

覆盖:
    - 简历图片 file_url → ProfileAgent → OCR + LLM 抽取 → long_term memory
    - 字段合并: name / email / phone / location / education / skills / experience / certifications / portfolio
    - 多次上传合并 (去重 + 累加)
    - OCR 失败兜底 (不抛,只是 ocr_notice 提示)
    - 内存 InMemoryStore 验证字段已经写入 long_term

E2E flow:
    POST /api/uploads → file_url
    POST /api/copilot (or 直接 run agent) with ctx.file_url → ProfileAgent
    → _maybe_ocr_resume → mock OCR provider → LLM extract → merge → memory write
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.jobseeker.profile_agent import ProfileAgent
from agents.runtime import AgentInput, MemoryScope


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class _MemoryWithLongTerm:
    """持久化所有 scope 的测试用 memory store (InMemoryStore 默认不存 long_term)。"""

    def __init__(self):
        self._store: dict[tuple, tuple] = {}

    async def write(self, scope, user_id, key, value):
        self._store[(scope.value if hasattr(scope, "value") else str(scope), user_id, key)] = value

    async def read(self, scope, user_id, key, default=None):
        s = scope.value if hasattr(scope, "value") else str(scope)
        return self._store.get((s, user_id, key), default)

    async def delete(self, scope, user_id, key):
        s = scope.value if hasattr(scope, "value") else str(scope)
        self._store.pop((s, user_id, key), None)

    async def list_keys(self, scope, user_id, prefix=""):
        s = scope.value if hasattr(scope, "value") else str(scope)
        return [
            k for (sc, u, k) in self._store
            if sc == s and u == user_id and k.startswith(prefix)
        ]


def _mock_ocr_provider():
    """返回伪造的 OCR + LLM 抽取链路。

    模拟行为:
        recognize_url(url) -> "简历原文 ..."
        parse_resume_from_url(url) -> 结构化 dict
    """
    sample_extracted = {
        "basic": {
            "name": "李雷",
            "email": "lilei@example.com",
            "phone": "13800001111",
            "location": "上海",
        },
        "education": [
            {"school": "清华大学", "degree": "本科", "major": "计算机", "year": "2018"},
        ],
        "experience": [
            {
                "company": "阿里巴巴",
                "title": "高级工程师",
                "duration_months": 48,
                "responsibilities": ["后端开发", "架构设计"],
                "achievements": ["优化系统性能 30%"],
            }
        ],
        "skills": [
            {"name": "Python", "category": "language", "years": 8, "level": "expert"},
            {"name": "PostgreSQL", "category": "db", "years": 5, "level": "advanced"},
        ],
        "certifications": [{"name": "PMP", "issuer": "PMI"}],
        "portfolio": [{"title": "GitHub", "url": "https://github.com/lilei"}],
        "interests": ["AI", "开源"],
        "highlights": [{"fact": "ACM 区域赛金牌", "significance": "算法能力突出"}],
        "overall_impression": "技术能力扎实的后端工程师",
    }

    parsed = {
        "source_url": "https://cdn.example.com/resumes/lilei.jpg",
        "raw_text": "李雷 男 13800001111 lilei@example.com ...",
        "language": "zh",
        "extracted": sample_extracted,
        "provider_chain": ["ocr", "llm"],
        "ocr_provider": "tencent",
    }
    return parsed


# ---------------------------------------------------------------------------
# 1. E2E — image → structured fields → long_term memory
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ocr_e2e_image_to_memory(mock_llm):
    """image file_url → ProfileAgent → 自动 OCR → 字段合并 → long_term 写入."""
    mem = _MemoryWithLongTerm()
    agent = ProfileAgent(llm=mock_llm, memory=mem)
    parsed = _mock_ocr_provider()

    with patch.object(
        ProfileAgent,
        "_maybe_ocr_resume",
        new=AsyncMock(return_value=parsed),
    ):
        inp = AgentInput(
            user_id="u1",
            persona="jobseeker",
            text="这是我的简历,请帮我整理成画像。",
            context={"file_url": "https://cdn.example.com/resumes/lilei.jpg"},
        )
        out = await agent.run(inp)

    assert out.success, out.error
    # artifacts 反映 OCR 触发了
    assert out.artifacts["ocr_triggered"] is True
    assert out.artifacts["ocr_provider"] == "tencent"
    # 字段合并到 long_term memory
    profile = out.artifacts["updated_profile"]
    assert profile["name"] == "李雷"
    assert profile["email"] == "lilei@example.com"
    assert profile["phone"] == "13800001111"
    assert profile["location"] == "上海"
    assert profile["education"][0]["school"] == "清华大学"
    assert any(s["name"] == "Python" for s in profile["skills"])
    assert profile["certifications"][0]["name"] == "PMP"
    assert profile["portfolio"][0]["title"] == "GitHub"
    assert profile["summary"] == "技术能力扎实的后端工程师"

    # long_term 真的写了
    mem_val = await mem.read(
        scope=MemoryScope.long_term,
        user_id="u1",
        key="profile",
        default=None,
    )
    assert mem_val is not None
    assert mem_val["name"] == "李雷"
    assert mem_val["_resume_source_url"] == "https://cdn.example.com/resumes/lilei.jpg"


# ---------------------------------------------------------------------------
# 2. 多次上传简历 → 字段合并 + 去重
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ocr_merge_multiple_uploads(mock_llm):
    """第二次上传时,已有 skills/edu 应合并而非覆盖。"""
    mem = _MemoryWithLongTerm()
    agent = ProfileAgent(llm=mock_llm, memory=mem)
    parsed1 = _mock_ocr_provider()
    parsed2 = _mock_ocr_provider()
    # 第二次简历多了一项 skill 和一个 edu
    parsed2["extracted"]["skills"].append({"name": "Kubernetes", "category": "devops", "years": 3, "level": "intermediate"})
    parsed2["extracted"]["education"].append({"school": "MIT", "degree": "硕士", "major": "CS"})

    with patch.object(ProfileAgent, "_maybe_ocr_resume", new=AsyncMock(return_value=parsed1)):
        await agent.run(AgentInput(
            user_id="u2",
            persona="jobseeker",
            text="上传第一份简历",
            context={"file_url": "https://x/resume1.jpg"},
        ))
    with patch.object(ProfileAgent, "_maybe_ocr_resume", new=AsyncMock(return_value=parsed2)):
        out2 = await agent.run(AgentInput(
            user_id="u2",
            persona="jobseeker",
            text="我又上传了一份更新的简历",
            context={"file_url": "https://x/resume2.jpg"},
        ))

    profile = out2.artifacts["updated_profile"]
    skill_names = {s["name"] for s in profile["skills"]}
    assert {"Python", "PostgreSQL", "Kubernetes"} <= skill_names
    edu_schools = {e["school"] for e in profile["education"]}
    assert {"清华大学", "MIT"} <= edu_schools
    # 基本字段不被覆盖
    assert profile["name"] == "李雷"


# ---------------------------------------------------------------------------
# 3. OCR 失败兜底
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ocr_failure_does_not_break(mock_llm):
    mem = _MemoryWithLongTerm()
    agent = ProfileAgent(llm=mock_llm, memory=mem)
    err = {"_error": "OCR provider unreachable", "source_url": "https://x/resume.jpg"}
    with patch.object(ProfileAgent, "_maybe_ocr_resume", new=AsyncMock(return_value=err)):
        out = await agent.run(AgentInput(
            user_id="u3",
            persona="jobseeker",
            text="解析失败的话你可以直接问我。",
            context={"file_url": "https://x/resume.jpg"},
        ))
    # 不抛
    assert out.success
    # artifacts 标记 OCR 触发了 + 错误
    assert out.artifacts["ocr_triggered"] is True
    # 头像应该有提示
    assert "解析失败" in out.text or "我记下了" in out.text


# ---------------------------------------------------------------------------
# 4. _merge_resume_into_profile 单元测试 (直接调用, 不走 OCR)
# ---------------------------------------------------------------------------
def test_merge_resume_dedup_skills():
    agent = ProfileAgent(llm=MagicMock(), memory=None)
    parsed = _mock_ocr_provider()
    # 第二次 (同名 skill, years 更新, level 已有就保留)
    parsed["extracted"]["skills"][0]["level"] = "master"
    parsed["extracted"]["skills"][0]["years"] = 10

    base = {"name": "李雷", "skills": [{"name": "Python", "category": "language", "years": 5, "level": "expert"}]}
    merged = agent._merge_resume_into_profile(base, parsed)
    py = next(s for s in merged["skills"] if s["name"] == "Python")
    # years 取较大值
    assert py["years"] == 10
    # level: 已有非空 → 保留
    assert py["level"] == "expert"


def test_merge_resume_basic_fields_filled_only_when_empty():
    agent = ProfileAgent(llm=MagicMock(), memory=None)
    parsed = _mock_ocr_provider()
    base = {"name": "自定义姓名", "email": "override@me.com", "phone": ""}
    merged = agent._merge_resume_into_profile(base, parsed)
    assert merged["name"] == "自定义姓名"
    assert merged["email"] == "override@me.com"
    assert merged["phone"] == "13800001111"  # 空的会被填


def test_merge_resume_highlights_and_summary():
    agent = ProfileAgent(llm=MagicMock(), memory=None)
    parsed = _mock_ocr_provider()
    base: dict = {}
    merged = agent._merge_resume_into_profile(base, parsed)
    assert "AI" in merged["interests"]
    assert merged["highlights"][0]["fact"] == "ACM 区域赛金牌"
    assert merged["summary"] == "技术能力扎实的后端工程师"


def test_merge_resume_provenance_recorded():
    agent = ProfileAgent(llm=MagicMock(), memory=None)
    parsed = _mock_ocr_provider()
    base: dict = {}
    merged = agent._merge_resume_into_profile(base, parsed)
    assert merged["_resume_source_url"] == "https://cdn.example.com/resumes/lilei.jpg"
    assert merged["_resume_ocr_provider"] == "tencent"
    assert "李雷" in merged["_resume_raw_text_snippet"]
    assert "_resume_last_parsed_at" in merged


# ---------------------------------------------------------------------------
# 5. long_term memory 单测 — 用真实 InMemoryStore
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_long_term_memory_persists_across_calls(mock_llm):
    mem = _MemoryWithLongTerm()
    agent = ProfileAgent(llm=mock_llm, memory=mem)
    parsed = _mock_ocr_provider()
    with patch.object(ProfileAgent, "_maybe_ocr_resume", new=AsyncMock(return_value=parsed)):
        await agent.run(AgentInput(
            user_id="u4", persona="jobseeker", text="hi",
            context={"file_url": "https://x/y.jpg"},
        ))
    # 第二次: 没有 file_url, 但应该能 recall
    out2 = await agent.run(AgentInput(user_id="u4", persona="jobseeker", text="我叫什么?"))
    assert out2.success
    # 验证: memory.read 直接拉
    val = await mem.read(scope=MemoryScope.long_term, user_id="u4", key="profile", default=None)
    assert val and val["name"] == "李雷"


# ---------------------------------------------------------------------------
# 6. 字段映射 — skills.name 必须 unique
# ---------------------------------------------------------------------------
def test_skills_uniqueness():
    agent = ProfileAgent(llm=MagicMock(), memory=None)
    parsed = _mock_ocr_provider()
    parsed["extracted"]["skills"].append({"name": "Python", "category": "language", "years": 99, "level": "wizard"})
    base: dict = {}
    merged = agent._merge_resume_into_profile(base, parsed)
    py_skills = [s for s in merged["skills"] if s["name"] == "Python"]
    assert len(py_skills) == 1


# ---------------------------------------------------------------------------
# 7. 空 parsed 不爆
# ---------------------------------------------------------------------------
def test_merge_with_empty_extracted():
    agent = ProfileAgent(llm=MagicMock(), memory=None)
    parsed = {"source_url": "x", "extracted": {}, "provider_chain": []}
    base = {"name": "已存在"}
    merged = agent._merge_resume_into_profile(base, parsed)
    assert merged["name"] == "已存在"
    assert "_resume_source_url" in merged


# ---------------------------------------------------------------------------
# 8. 没有 file_url → 不触发 OCR
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_file_url_no_ocr(mock_llm, mock_memory):
    agent = ProfileAgent(llm=mock_llm, memory=mock_memory)
    with patch.object(ProfileAgent, "_maybe_ocr_resume", new=AsyncMock(return_value=None)) as m:
        out = await agent.run(AgentInput(
            user_id="u5", persona="jobseeker", text="我叫韩梅梅",
            context={},
        ))
    assert out.artifacts["ocr_triggered"] is False
    m.assert_awaited_once()


# ---------------------------------------------------------------------------
# 9. resume_parser 实际拉取路径 — 用 httpx mock
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_real_resume_parser_path(mock_llm, mock_memory):
    """端到端真实路径: profile_agent → resume_parser.parse_resume_from_url."""
    from PIL import Image

    agent = ProfileAgent(llm=mock_llm, memory=mock_memory)

    # 模拟远程图片
    import io as _io
    img = Image.new("RGB", (100, 100), color=(255, 255, 255))
    buf = _io.BytesIO()
    img.save(buf, format="PNG")
    raw_bytes = buf.getvalue()

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=MagicMock(
        content=raw_bytes, raise_for_status=MagicMock(),
    ))), patch("providers.registry.get_ocr_provider", return_value=MagicMock(
        recognize_url=AsyncMock(return_value=MagicMock(text="李雷 13800001111 Python 后端")),
    )):
        # 直接调用 _maybe_ocr_resume
        result = await agent._maybe_ocr_resume({
            "file_url": "https://x/resume.png",
        })
    assert result is not None
    assert result["source_url"] == "https://x/resume.png"
    assert "李雷" in result.get("raw_text", "") or "李雷" in str(result.get("extracted", ""))


# ---------------------------------------------------------------------------
# 10. 异常 OCR provider → 返回 _error dict
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ocr_provider_exception_returns_error_dict(mock_llm):
    mem = _MemoryWithLongTerm()
    agent = ProfileAgent(llm=mock_llm, memory=mem)
    with patch("services.resume_parser.parse_resume_from_url", new=AsyncMock(side_effect=RuntimeError("down"))):
        result = await agent._maybe_ocr_resume({"file_url": "https://x/y.jpg"})
    assert result and "_error" in result
    assert "down" in result["_error"]
    assert result["source_url"] == "https://x/y.jpg"