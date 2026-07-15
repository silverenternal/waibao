"""PaddleOCR 本地 Provider (v11.0 / T6102).

第三方简历 / 资质材料数据 **完全不允许离开甲方环境** —— PaddleOCR 在
甲方内网本地运行,所有图片像素 + 识别文字全程不出网 (``recognize_url``
仅在调用方显式给 URL 时下载图片,识别仍在本机完成)。

设计要点
--------
1. **完全本地推理**。用 ``paddleocr`` Python 库 (CPU/GPU 自适配),不调用
   任何外部 OCR SaaS。模型走 ``PADDLE_OCR_MODEL_DIR`` 预下载目录,离线启动
   不联网拉权重。
2. **懒导入 + 懒初始化**。``paddleocr`` 依赖 paddle / opencv 等重量级包,
   本地开发机多半没装 —— 因此把 ``import paddleocr`` 延迟到 ``__init__``
   /首次推理,保证 registry 在未安装 paddleocr 的环境里也能正常 import
   其它 provider。真正缺失时,构造阶段抛清晰的 ``ProviderError``。
3. **CPU 推理走线程池**。PaddleOCR 的 ``predict``/``ocr`` 是同步阻塞调用,
   直接在 event loop 里跑会卡住整个进程 —— 通过
   ``asyncio.get_running_loop().run_in_executor`` 卸到默认线程池。
4. **中文 + 英文**。``PaddleOCR(lang="ch")`` 同时识别中英文 (PaddleOCR 的
   ``ch`` 模型本身含英文;``en`` 纯英文)。``language`` 参数映射到 PaddleOCR
   的 ``lang``。
5. 复用统一 ``OCRResult`` / ``OCRProvider`` 契约,无缝替换腾讯/百度 OCR。
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import tempfile
from typing import Any

from ..exceptions import InvalidRequestError, ProviderError
from .base import OCRProvider, OCRResult

logger = logging.getLogger(__name__)

# language 入参 -> PaddleOCR lang 的映射
_LANG_MAP: dict[str, str] = {
    "auto": "ch",  # auto 默认走中文模型 (含英文),简历/资质最常见场景
    "zh": "ch",
    "ch": "ch",
    "chinese": "ch",
    "en": "en",
    "english": "en",
}


class PaddleOCRProvider(OCRProvider):
    """PaddleOCR 本地 OCR,数据全程不出甲方环境."""

    provider_name = "paddle"

    ENV_MODEL_DIR: str = "PADDLE_OCR_MODEL_DIR"
    ENV_USE_GPU: str = "PADDLE_OCR_USE_GPU"
    ENV_LANG: str = "PADDLE_OCR_LANG"
    ENV_USE_ANGLE_CLS: str = "PADDLE_OCR_USE_ANGLE_CLS"
    DEFAULT_LANG: str = "ch"
    DEFAULT_MIME: str = "image/png"

    def __init__(
        self,
        *,
        model_dir: str | None = None,
        lang: str | None = None,
        use_gpu: bool | None = None,
        use_angle_cls: bool | None = None,
        **kwargs: Any,
    ) -> None:
        self.model_dir = (
            model_dir or os.getenv(self.ENV_MODEL_DIR, "").strip() or None
        )
        self.lang = (lang or os.getenv(self.ENV_LANG, "") or self.DEFAULT_LANG).lower()
        self.use_gpu = (
            use_gpu
            if use_gpu is not None
            else os.getenv(self.ENV_USE_GPU, "").strip().lower() in ("1", "true", "yes", "on")
        )
        self.use_angle_cls = (
            use_angle_cls
            if use_angle_cls is not None
            else os.getenv(self.ENV_USE_ANGLE_CLS, "1").strip().lower()
            in ("1", "true", "yes", "on")
        )
        self._engine: Any | None = None  # 懒初始化 (首次 recognize 才真正加载权重)
        self._engine_lang: str | None = None

    # ------------------------------------------------------------------
    # 引擎生命周期
    # ------------------------------------------------------------------
    def _resolve_lang(self, language: str) -> str:
        key = (language or "auto").strip().lower()
        return _LANG_MAP.get(key, self.lang)

    def _build_engine(self, lang: str) -> Any:
        """构造 PaddleOCR 引擎。失败抛 ProviderError (retryable=True)."""
        try:
            # 延迟导入: paddleocr 是重量级依赖,本地/CI 未安装时不应阻断 import 链
            try:
                from paddleocr import PaddleOCR  # type: ignore[import-not-found]
            except ImportError as exc:  # pragma: no cover - 环境依赖
                raise ProviderError(
                    "paddleocr 未安装 — 在 backend 容器内 "
                    "`pip install paddleocr paddlepaddle`,"
                    "或改用 OCR_PROVIDER=mock/其它云端 provider",
                    provider="paddle_ocr",
                    retryable=True,
                ) from exc

            kwargs: dict[str, Any] = {
                "lang": lang,
                "use_angle_cls": self.use_angle_cls,
                "use_gpu": self.use_gpu,
                "show_log": False,
            }
            if self.model_dir:
                kwargs["det_model_dir"] = os.path.join(self.model_dir, "det")
                kwargs["rec_model_dir"] = os.path.join(self.model_dir, "rec")
                kwargs["cls_model_dir"] = os.path.join(self.model_dir, "cls")
            return PaddleOCR(**kwargs)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 - paddle 内部异常统一映射
            raise ProviderError(
                f"paddleocr 引擎初始化失败: {exc}", provider="paddle_ocr", retryable=True
            ) from exc

    def _get_engine(self, lang: str) -> Any:
        """懒加载 + 按 lang 复用单例。lang 切换时重建引擎。"""
        if self._engine is None or self._engine_lang != lang:
            logger.info(
                "paddle_ocr 初始化引擎 lang=%s gpu=%s model_dir=%s",
                lang, self.use_gpu, self.model_dir,
            )
            self._engine = self._build_engine(lang)
            self._engine_lang = lang
        return self._engine

    # ------------------------------------------------------------------
    # 解析 paddle 返回 -> OCRResult
    # ------------------------------------------------------------------
    @staticmethod
    def _flatten_bbox(raw_bbox: Any) -> list[float]:
        """把 PaddleOCR 的 bbox 归一化成扁平 float list.

        PaddleOCR 的检测框是四点多边形 ``[[x1,y1],[x2,y2],[x3,y3],[x4,y4]]``
        (numpy array 时带 ``.tolist()``);少数版本给扁平 ``[x1,y1,x2,y2,...]``。
        本函数递归拍平成纯 ``float`` 一维数组,两种结构都兼容。
        """
        if hasattr(raw_bbox, "tolist"):
            raw_bbox = raw_bbox.tolist()

        out: list[float] = []

        def _walk(node: Any) -> None:
            if isinstance(node, (list, tuple)):
                for n in node:
                    _walk(n)
            else:
                try:
                    out.append(float(node))
                except (TypeError, ValueError):
                    pass

        _walk(raw_bbox)
        return out

    @classmethod
    def _parse_result(cls, raw: Any) -> OCRResult:
        """把 PaddleOCR ocr() 返回值归一化成 OCRResult.

        PaddleOCR 不同版本返回结构略有差异:
          * v2.x (res[0]) -> list[[bbox, (text, conf)], ...]
          * v3.x          -> list[ dict(dt_polys, rec_texts, rec_scores) ]
        这里两套都兼容。
        """
        blocks: list[dict[str, Any]] = []
        texts: list[str] = []
        confs: list[float] = []

        # res 通常是 [page0_result]; 取第一页
        page = raw[0] if isinstance(raw, (list, tuple)) and raw else raw
        items: list[Any]
        if isinstance(page, dict):
            # v3.x dict 结构
            polys = page.get("dt_polys") or page.get("rec_polys") or []
            rec_texts = page.get("rec_texts") or []
            rec_scores = page.get("rec_scores") or []
            for idx, poly in enumerate(polys):
                txt = rec_texts[idx] if idx < len(rec_texts) else ""
                conf = float(rec_scores[idx]) if idx < len(rec_scores) else 0.0
                bbox = cls._flatten_bbox(poly)
                blocks.append({"text": txt, "bbox": bbox, "confidence": conf})
                texts.append(txt)
                confs.append(conf)
        elif isinstance(page, (list, tuple)):
            items = list(page)
            for item in items:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    bbox_raw, txt_info = item[0], item[1]
                    if isinstance(txt_info, (list, tuple)) and txt_info:
                        txt, conf = txt_info[0], float(txt_info[1])
                    elif isinstance(txt_info, str):
                        txt, conf = txt_info, 0.0
                    else:
                        txt, conf = str(txt_info), 0.0
                    bbox = cls._flatten_bbox(bbox_raw)
                    blocks.append({"text": txt, "bbox": bbox, "confidence": conf})
                    texts.append(txt)
                    confs.append(conf)
        text = "\n".join(t for t in texts if t)
        confidence = sum(confs) / len(confs) if confs else 0.0
        return OCRResult(
            text=text,
            blocks=blocks,
            confidence=confidence,
            raw=raw,
        )

    # ------------------------------------------------------------------
    # 同步推理 (在线程池里跑)
    # ------------------------------------------------------------------
    def _recognize_sync(self, image_path: str, lang: str) -> Any:
        engine = self._get_engine(lang)
        result = engine.ocr(image_path, cls=self.use_angle_cls)
        return result

    # ------------------------------------------------------------------
    # 公开契约
    # ------------------------------------------------------------------
    async def recognize(
        self,
        image: bytes,
        *,
        mime: str = "image/png",
        language: str = "auto",
        **kwargs: Any,
    ) -> OCRResult:
        if not image:
            raise InvalidRequestError(
                "paddle_ocr.recognize 收到空 image bytes", provider="paddle_ocr"
            )
        lang = self._resolve_lang(language)
        ext = _mime_to_ext(mime)
        # PaddleOCR 接受文件路径 —— 写临时文件 (推理完即删)
        tmp = tempfile.NamedTemporaryFile(
            prefix="waibao_paddle_", suffix=f".{ext}", delete=False
        )
        try:
            tmp.write(image)
            tmp.flush()
            tmp.close()
            loop = asyncio.get_running_loop()
            raw = await loop.run_in_executor(None, self._recognize_sync, tmp.name, lang)
            return self._parse_result(raw)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                f"paddleocr 识别失败: {exc}", provider="paddle_ocr", retryable=True
            ) from exc
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    async def recognize_url(
        self,
        url: str,
        *,
        language: str = "auto",
        **kwargs: Any,
    ) -> OCRResult:
        """下载图片到内存再本地识别 —— 图片不进任何外部 OCR 服务."""
        if not url:
            raise InvalidRequestError(
                "paddle_ocr.recognize_url 收到空 url", provider="paddle_ocr"
            )
        import httpx

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                image = resp.content
                mime = resp.headers.get("content-type", self.DEFAULT_MIME).split(";")[0].strip()
        except httpx.HTTPStatusError as exc:
            raise _map_http(exc) from exc
        except (httpx.RequestError, OSError) as exc:
            raise ProviderError(
                f"paddle_ocr 下载图片失败 ({url}): {exc}",
                provider="paddle_ocr",
                retryable=True,
            ) from exc
        return await self.recognize(image, mime=mime, language=language)


def _mime_to_ext(mime: str) -> str:
    m = (mime or "").split(";")[0].strip().lower()
    return {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/webp": "webp",
        "image/bmp": "bmp",
        "image/tiff": "tif",
    }.get(m, "png")


def _map_http(exc: Exception) -> ProviderError:
    """httpx HTTPStatusError -> ProviderError 子类映射."""
    from ..exceptions import (
        AuthError,
        InvalidRequestError,
        RateLimitError,
        UpstreamUnavailableError,
    )

    code = getattr(getattr(exc, "response", None), "status_code", 0)
    msg = str(exc)
    if code in (401, 403):
        return AuthError(msg, provider="paddle_ocr")
    if code == 429:
        return RateLimitError(msg, provider="paddle_ocr")
    if 400 <= code < 500:
        return InvalidRequestError(msg, provider="paddle_ocr")
    return UpstreamUnavailableError(msg, provider="paddle_ocr")
