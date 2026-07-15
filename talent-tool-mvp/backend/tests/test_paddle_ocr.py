"""PaddleOCR 本地 Provider 单元测试 (v11.0 / T6102).

覆盖目标:
    1. paddleocr 响应解析 (v2.x list 结构 + v3.x dict 结构) -> OCRResult
    2. recognize / recognize_url 主路径 (mock 掉引擎 + httpx)
    3. recognize_url 下载失败异常映射 (ProviderError / Auth / RateLimit)
    4. paddleocr 缺失时懒导入抛 ProviderError (不影响 import 链)
    5. OCR_PROVIDER=paddle 时 registry 返回 PaddleOCRProvider
    6. OCR_PROVIDER 未设时 v11.0 默认本地 paddle
    7. fallback 链: paddle 缺依赖时显式 mock 仍可用
    8. 中文 / 英文 language 映射
"""
from __future__ import annotations

import os
import sys
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

# 把项目根 + backend 加入 sys.path,与其它 provider 测试一致
_THIS = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_THIS)            # .../talent-tool-mvp/backend
_PROJECT = os.path.dirname(_BACKEND)         # .../talent-tool-mvp
for _p in (_PROJECT, _BACKEND):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backend.providers import exceptions, registry  # noqa: E402
from backend.providers.exceptions import (  # noqa: E402
    AuthError,
    InvalidRequestError,
    ProviderError,
    RateLimitError,
    UpstreamUnavailableError,
)
from backend.providers.ocr.mock_provider import MockOCRProvider  # noqa: E402
from backend.providers.ocr.paddle_ocr import (  # noqa: E402
    PaddleOCRProvider,
    _LANG_MAP,
    _mime_to_ext,
)


@pytest.fixture(autouse=True)
def _reset_registry(monkeypatch: pytest.MonkeyPatch):
    """每个用例前后清掉 registry 单例,避免互相污染。"""
    registry.reset_cache()
    yield
    registry.reset_cache()


# ===========================================================================
# 1. 静态解析逻辑 (不依赖真实 paddleocr)
# ===========================================================================
class TestParseResult:
    def test_parse_v2_list_structure(self):
        """PaddleOCR v2.x: ocr() -> [ page0 ], page0 = [ [bbox, (text, conf)], ... ]"""
        bbox1 = [[0, 0], [100, 0], [100, 20], [0, 20]]
        bbox2 = [[0, 30], [100, 30], [100, 50], [0, 50]]
        item1 = [bbox1, ("张三", 0.98)]
        item2 = [bbox2, ("前端工程师", 0.95)]
        raw = [[item1, item2]]  # [page0]
        result = PaddleOCRProvider._parse_result(raw)
        assert result.text == "张三\n前端工程师"
        assert len(result.blocks) == 2
        assert result.blocks[0]["text"] == "张三"
        assert result.blocks[0]["confidence"] == pytest.approx(0.98)
        # 四点框拍平成 8 个 float
        assert result.blocks[0]["bbox"] == [0.0, 0.0, 100.0, 0.0, 100.0, 20.0, 0.0, 20.0]
        assert result.confidence == pytest.approx(0.965, rel=1e-3)
        assert result.raw is raw

    def test_parse_v3_dict_structure(self):
        """PaddleOCR v3.x: ocr() -> [ {dt_polys, rec_texts, rec_scores} ]."""
        page0 = {
            "dt_polys": [[[[0, 0], [50, 0], [50, 20], [0, 20]]]],
            "rec_texts": ["Hello"],
            "rec_scores": [0.91],
        }
        result = PaddleOCRProvider._parse_result([page0])  # [page0]
        assert result.text == "Hello"
        assert result.blocks[0]["text"] == "Hello"
        assert result.blocks[0]["confidence"] == pytest.approx(0.91)

    def test_parse_empty(self):
        result = PaddleOCRProvider._parse_result([[]])
        assert result.text == ""
        assert result.blocks == []
        assert result.confidence == 0.0

    def test_parse_skips_empty_text(self):
        bbox = [[0, 0], [1, 0], [1, 1], [0, 1]]
        item1 = [bbox, ("", 0.5)]
        item2 = [bbox, ("ok", 0.9)]
        result = PaddleOCRProvider._parse_result([[item1, item2]])
        assert result.text == "ok"  # 空 text 被 join 过滤


# ===========================================================================
# 2. 语言映射 + mime 工具
# ===========================================================================
class TestLangAndMime:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            ("auto", "ch"),
            ("zh", "ch"),
            ("chinese", "ch"),
            ("en", "en"),
            ("english", "en"),
            ("CH", "ch"),  # 大小写不敏感
        ],
    )
    def test_lang_map(self, inp: str, expected: str):
        assert _LANG_MAP[inp.lower()] == expected

    def test_resolve_lang_falls_back_to_default(self):
        p = PaddleOCRProvider(lang="ch")
        # 未知语言回落到 provider 默认 lang
        assert p._resolve_lang("klingon") == "ch"

    @pytest.mark.parametrize(
        "mime,ext",
        [
            ("image/png", "png"),
            ("image/jpeg", "jpg"),
            ("image/webp", "webp"),
            ("image/bmp", "bmp"),
            ("application/octet-stream", "png"),  # 未知 -> png
            ("image/png; charset=binary", "png"),  # 带 params
        ],
    )
    def test_mime_to_ext(self, mime: str, ext: str):
        assert _mime_to_ext(mime) == ext


# ===========================================================================
# 3. recognize 主路径 (mock 引擎)
# ===========================================================================
def _make_provider_with_engine(engine_ret: Any) -> PaddleOCRProvider:
    p = PaddleOCRProvider(lang="ch")
    # 跳过真实 paddleocr 初始化,直接注入 mock 引擎
    engine = MagicMock()
    engine.ocr = MagicMock(return_value=engine_ret)
    p._engine = engine
    p._engine_lang = "ch"
    return p


class TestRecognize:
    async def test_recognize_returns_text(self):
        bbox = [[0, 0], [80, 0], [80, 24], [0, 24]]
        item = [bbox, ("Java 工程师", 0.97)]
        ret = [[item]]  # [page0]
        p = _make_provider_with_engine(ret)
        result = await p.recognize(b"fake-png-bytes", mime="image/png")
        assert "Java 工程师" in result.text
        assert result.blocks[0]["confidence"] == pytest.approx(0.97)
        # engine.ocr 被以文件路径调用
        assert engine_called_with_path(p)

    async def test_recognize_empty_bytes_raises(self):
        p = _make_provider_with_engine([])
        with pytest.raises(InvalidRequestError):
            await p.recognize(b"", mime="image/png")

    async def test_recognize_engine_failure_wrapped(self):
        p = _make_provider_with_engine(None)
        p._engine.ocr = MagicMock(side_effect=RuntimeError("segfault"))
        with pytest.raises(ProviderError) as exc:
            await p.recognize(b"img", mime="image/png")
        assert "segfault" in str(exc.value)
        assert exc.value.retryable is True

    async def test_recognize_language_switch_rebuilds_engine(self, monkeypatch):
        """切换 language 应触发引擎重建 (engine_lang != lang)."""
        built = MagicMock()
        monkeypatch.setattr(PaddleOCRProvider, "_build_engine", lambda self, lang: built)
        built.ocr = MagicMock(return_value=[[[]]])
        p = PaddleOCRProvider(lang="ch")
        p._engine = MagicMock()
        p._engine_lang = "ch"
        await p.recognize(b"img", language="en")
        # en 触发重建
        assert p._engine_lang == "en"


def engine_called_with_path(p: PaddleOCRProvider) -> bool:
    args, _ = p._engine.ocr.call_args
    return isinstance(args[0], str) and args[0].endswith(".png")


# ===========================================================================
# 4. recognize_url 下载 + 异常映射
# ===========================================================================
class TestRecognizeUrl:
    async def test_recognize_url_downloads_then_recognizes(self, monkeypatch):
        p = _make_provider_with_engine([[[]]])

        class FakeResp:
            content = b"img-bytes"
            status_code = 200
            headers = {"content-type": "image/jpeg"}

            def raise_for_status(self):
                pass

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url):
                self.last_url = url
                return FakeResp()

        monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
        result = await p.recognize_url("https://internal/img.jpg")
        assert result is not None
        # mime 从 content-type 传到 recognize -> 临时文件后缀
        args, _ = p._engine.ocr.call_args
        assert args[0].endswith(".jpg")

    async def test_recognize_url_empty_raises(self):
        p = _make_provider_with_engine([])
        with pytest.raises(InvalidRequestError):
            await p.recognize_url("")

    @pytest.mark.parametrize(
        "status,exc_cls",
        [
            (401, AuthError),
            (403, AuthError),
            (429, RateLimitError),
            (404, InvalidRequestError),
            (500, UpstreamUnavailableError),
        ],
    )
    async def test_recognize_url_http_errors_mapped(
        self, monkeypatch, status: int, exc_cls: type
    ):
        p = _make_provider_with_engine([])

        req = httpx.Request("GET", "https://x/img")
        resp = httpx.Response(status, request=req, text="nope")

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url):
                err = httpx.HTTPStatusError("err", request=req, response=resp)
                raise err

        monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
        with pytest.raises(exc_cls):
            await p.recognize_url("https://x/img")

    async def test_recognize_url_network_error_wrapped(self, monkeypatch):
        p = _make_provider_with_engine([])

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url):
                raise httpx.ConnectError("conn refused")

        monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
        with pytest.raises(ProviderError) as exc:
            await p.recognize_url("https://x/img")
        assert exc.value.retryable is True


# ===========================================================================
# 5. 懒导入 / 缺依赖行为
# ===========================================================================
class TestLazyImport:
    def test_import_does_not_require_paddleocr(self):
        """paddleocr 未安装时,模块本身仍能 import (懒导入)。"""
        # 若到这一步说明 import 成功
        assert PaddleOCRProvider.provider_name == "paddle"

    def test_build_engine_raises_when_paddleocr_missing(self, monkeypatch):
        """paddleocr 缺失时 _build_engine 抛 ProviderError (retryable)。"""
        monkeypatch.setitem(sys.modules, "paddleocr", None)
        # 强制 import 失败
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "paddleocr":
                raise ImportError("no paddleocr")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        p = PaddleOCRProvider(lang="ch")
        with pytest.raises(ProviderError) as exc:
            p._build_engine("ch")
        assert "paddleocr" in str(exc.value).lower()
        assert exc.value.retryable is True

    async def test_recognize_raises_provider_error_when_engine_init_fails(
        self, monkeypatch
    ):
        """引擎初始化抛 ProviderError 时,recognize 直接传播 (不被吞成别的)."""
        monkeypatch.setattr(
            PaddleOCRProvider,
            "_build_engine",
            lambda self, lang: (_ for _ in ()).throw(
                ProviderError("init boom", provider="paddle_ocr", retryable=True)
            ),
        )
        p = PaddleOCRProvider(lang="ch")
        with pytest.raises(ProviderError, match="init boom"):
            await p.recognize(b"img", mime="image/png")


# ===========================================================================
# 6. registry 路由 (OCR_PROVIDER=paddle / 默认)
# ===========================================================================
class TestRegistryRouting:
    def test_paddle_selected_when_env_paddle(self, monkeypatch):
        monkeypatch.setenv("OCR_PROVIDER", "paddle")
        registry.reset_cache()
        p = registry.get_ocr_provider()
        assert isinstance(p, PaddleOCRProvider)
        assert p.provider_name == "paddle"

    def test_default_is_paddle_when_env_unset(self, monkeypatch):
        """v11.0: 没有 OCR_PROVIDER 时默认本地 paddle (数据不出网)."""
        monkeypatch.delenv("OCR_PROVIDER", raising=False)
        registry.reset_cache()
        p = registry.get_ocr_provider()
        assert isinstance(p, PaddleOCRProvider)

    def test_mock_still_selectable(self, monkeypatch):
        monkeypatch.setenv("OCR_PROVIDER", "mock")
        registry.reset_cache()
        assert isinstance(registry.get_ocr_provider(), MockOCRProvider)

    def test_unknown_provider_raises(self, monkeypatch):
        monkeypatch.setenv("OCR_PROVIDER", "no-such-ocr")
        registry.reset_cache()
        with pytest.raises(exceptions.InvalidRequestError):
            registry.get_ocr_provider()


# ===========================================================================
# 7. fallback 链
# ===========================================================================
class TestFallbackChain:
    def test_explicit_mock_fallback(self, monkeypatch):
        """paddle 不可用时显式 OCR_PROVIDER=mock 必须可用 (开发/测试降级)."""
        monkeypatch.setenv("OCR_PROVIDER", "mock")
        registry.reset_cache()
        p = registry.get_ocr_provider()
        assert isinstance(p, MockOCRProvider)

    def test_paddle_provider_is_real_local_not_mock(self, monkeypatch):
        """关键: paddle 是真实本地 provider,provider_name != 'mock'."""
        monkeypatch.setenv("OCR_PROVIDER", "paddle")
        registry.reset_cache()
        p = registry.get_ocr_provider()
        assert not isinstance(p, MockOCRProvider)
        assert p.provider_name == "paddle"

    async def test_mock_returns_fixed_text_vs_paddle_parsed(self, monkeypatch):
        """mock 走固定占位,paddle 走真实解析 —— 两者行为可区分。"""
        mock_p = MockOCRProvider()
        mock_res = await mock_p.recognize(b"x")
        assert mock_res.text.startswith("[mock-ocr]")

        bbox = [[0, 0], [10, 0], [10, 10], [0, 10]]
        item = [bbox, ("real text", 0.9)]
        paddle_p = _make_provider_with_engine([[item]])  # [page0]
        pad_res = await paddle_p.recognize(b"x")
        assert pad_res.text == "real text"
        assert not pad_res.text.startswith("[mock-ocr]")


# ===========================================================================
# 8. __init__ 配置读取
# ===========================================================================
class TestProviderConfig:
    def test_reads_env_defaults(self, monkeypatch):
        monkeypatch.setenv("PADDLE_OCR_MODEL_DIR", "/models/paddle")
        monkeypatch.setenv("PADDLE_OCR_LANG", "en")
        monkeypatch.setenv("PADDLE_OCR_USE_GPU", "true")
        monkeypatch.setenv("PADDLE_OCR_USE_ANGLE_CLS", "false")
        p = PaddleOCRProvider()
        assert p.model_dir == "/models/paddle"
        assert p.lang == "en"
        assert p.use_gpu is True
        assert p.use_angle_cls is False

    def test_explicit_kwargs_override_env(self, monkeypatch):
        monkeypatch.setenv("PADDLE_OCR_LANG", "en")
        p = PaddleOCRProvider(lang="ch", use_gpu=True)
        assert p.lang == "ch"
        assert p.use_gpu is True

    def test_default_lang_ch(self):
        p = PaddleOCRProvider()
        assert p.lang == "ch"
        assert p.use_gpu is False
        assert p.use_angle_cls is True
