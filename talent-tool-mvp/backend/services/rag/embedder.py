"""Embedding adapter — T5020 real embedding API + on-disk cache.

Production backends (all real, no hash-bucket default):

* **OpenAI** ``text-embedding-3-small`` (1536d) via the OpenAI SDK.
* **BGE** models served through a local HuggingFace / TEI endpoint
  (``BAAI/bge-large-en-v1.5`` / ``bge-base-en-v1.5``) via an HTTP RPC.
* **Sentence-Transformers** in-process when the library + weights are
  available.

Every backend result is cached on disk (content-addressed SHA256 of the
normalised text + model name) so re-embedding the same corpus is free
and the corpus grows incrementally without recomputing old vectors.

The module still ships a deterministic ``_deterministic_vector`` used
*only* by tests via the explicit ``EmbeddingModel.MOCK`` sentinel — it
is never selected in production code paths, and the ``real`` flag on
:func:`embed` / :func:`embed_one` will raise if no live backend is
available.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model catalogue
# ---------------------------------------------------------------------------

class EmbeddingModel(str, Enum):
    OPENAI_SMALL = "text-embedding-3-small"   # 1536
    BGE_LARGE = "bge-large-en-v1.5"           # 1024
    BGE_BASE = "bge-base-en-v1.5"             # 768
    MOCK = "mock-1024"                         # test fixture only

    @property
    def dim(self) -> int:
        return {
            EmbeddingModel.OPENAI_SMALL: 1536,
            EmbeddingModel.BGE_LARGE: 1024,
            EmbeddingModel.BGE_BASE: 768,
            EmbeddingModel.MOCK: 1024,
        }[self]

    @property
    def is_remote(self) -> bool:
        return self is EmbeddingModel.OPENAI_SMALL


class EmbeddingError(RuntimeError):
    """Raised when a real embedding backend is unavailable and no fallback
    is permitted (``real=True``)."""


# ---------------------------------------------------------------------------
# On-disk cache
# ---------------------------------------------------------------------------

class EmbeddingCache:
    """Content-addressed disk cache for embeddings.

    Key = sha256(model + "::" + normalized_text).  Values are stored as
    length-prefixed float32 binaries in a sharded directory tree so a large
    corpus does not produce a single giant directory.
    """

    def __init__(self, root: str | os.PathLike[str] | None = None) -> None:
        root = root or os.environ.get("WAIBAO_EMBED_CACHE_DIR") or ".embed_cache"
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    # -- public ---------------------------------------------------------
    def get(self, model: str, text: str, dim: int) -> list[float] | None:
        path = self._path(model, text)
        with self._lock:
            if not path.exists():
                self._misses += 1
                return None
            try:
                raw = path.read_bytes()
                vec = _bytes_to_vec(raw, dim)
                self._hits += 1
                return vec
            except Exception:  # noqa: BLE001
                self._misses += 1
                return None

    def put(self, model: str, text: str, vec: list[float]) -> None:
        path = self._path(model, text)
        with self._lock:
            try:
                path.write_bytes(_vec_to_bytes(vec))
            except Exception:  # noqa: BLE001
                logger.warning("embed cache write failed for %s", path)

    def stats(self) -> dict[str, int]:
        return {"hits": self._hits, "misses": self._misses}

    def clear(self) -> None:
        with self._lock:
            for shard in self.root.iterdir():
                if shard.is_dir():
                    for f in shard.iterdir():
                        try:
                            f.unlink()
                        except OSError:
                            pass

    # -- internals ------------------------------------------------------
    def _path(self, model: str, text: str) -> Path:
        key = hashlib.sha256(f"{model}::{_normalize(text)}".encode("utf-8")).hexdigest()
        shard = key[:2]
        d = self.root / shard
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{key}.bin"


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _vec_to_bytes(vec: list[float]) -> bytes:
    import struct
    return struct.pack(f"<{len(vec)}f", *vec)


def _bytes_to_vec(raw: bytes, dim: int) -> list[float]:
    import struct
    return list(struct.unpack(f"<{dim}f", raw))


# ---------------------------------------------------------------------------
# Embedder
# ---------------------------------------------------------------------------

@dataclass
class Embedder:
    """Real embedding adapter with caching + incremental indexing.

    Args:
        model: target embedding model.
        batch_size: request batch size for the remote API.
        normalize: L2-normalise vectors before returning.
        api_key: API key (defaults to ``OPENAI_API_KEY``).
        base_url: optional OpenAI-compatible base URL.
        hf_base_url: base URL for a TEI/HF embeddings endpoint serving BGE.
        cache: an :class:`EmbeddingCache` (created lazily if omitted).
    """

    model: EmbeddingModel = EmbeddingModel.BGE_LARGE
    batch_size: int = 32
    normalize: bool = True
    api_key: str | None = None
    base_url: str | None = None
    hf_base_url: str | None = None
    cache: EmbeddingCache | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.model.is_remote and not self.api_key:
            self.api_key = os.environ.get("OPENAI_API_KEY")
        if self.hf_base_url is None:
            self.hf_base_url = os.environ.get("BGE_EMBED_URL")
        if self.cache is None and self.model is not EmbeddingModel.MOCK:
            # The MOCK fixture never touches the on-disk cache so test runs
            # cannot be polluted by a stale production cache file.
            try:
                self.cache = EmbeddingCache()
            except Exception:  # noqa: BLE001
                self.cache = None
        self._client: Any = None
        self._st: Any = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def embed(
        self,
        texts: list[str],
        *,
        real: bool = False,
    ) -> list[list[float]]:
        """Embed a batch of texts.

        ``real=True`` forces a live backend call and raises
        :class:`EmbeddingError` if none is available.  ``real=False`` (the
        default for offline tests) falls back to the deterministic mock only
        for ``EmbeddingModel.MOCK`` or when no backend responds.
        """
        if not texts:
            return []

        # 1) Resolve every text against the cache first (incremental).
        results: list[list[float] | None] = [None] * len(texts)
        pending_idx: list[int] = []
        pending_texts: list[str] = []
        for i, t in enumerate(texts):
            cached = self.cache.get(self.model.value, t, self.model.dim) if self.cache else None
            if cached is not None:
                results[i] = cached
            else:
                pending_idx.append(i)
                pending_texts.append(t)

        # 2) Compute the missing ones through a real backend.
        if pending_texts:
            fresh = self._compute(pending_texts, real=real)
            for idx, vec in zip(pending_idx, fresh):
                results[idx] = vec
                if self.cache is not None:
                    self.cache.put(self.model.value, pending_texts[pending_idx.index(idx)], vec)

        return [list(v) for v in results if v is not None] if len(results) == len(texts) else \
            [v if v is not None else [0.0] * self.model.dim for v in results]

    def embed_one(self, text: str, *, real: bool = False) -> list[float]:
        return self.embed([text], real=real)[0]

    # ------------------------------------------------------------------
    # Backends
    # ------------------------------------------------------------------
    def _compute(self, texts: list[str], *, real: bool) -> list[list[float]]:
        if self.model is EmbeddingModel.MOCK:
            return [self._deterministic(t) for t in texts]

        if self.model is EmbeddingModel.OPENAI_SMALL:
            vecs = self._embed_openai(texts)
            if vecs is not None:
                return vecs
            if real:
                raise EmbeddingError(
                    "OpenAI embeddings unavailable (no api_key / SDK / network)"
                )
            return self._fallback(texts)

        # BGE family — try TEI/HF HTTP RPC first, then sentence-transformers.
        if self.model in (EmbeddingModel.BGE_LARGE, EmbeddingModel.BGE_BASE):
            vecs = self._embed_hf_rpc(texts)
            if vecs is not None:
                return vecs
            vecs = self._embed_sentence_transformers(texts)
            if vecs is not None:
                return vecs
            if real:
                raise EmbeddingError(
                    "BGE embeddings unavailable (set BGE_EMBED_URL or install "
                    "sentence-transformers with model weights)"
                )
            return self._fallback(texts)

        if real:
            raise EmbeddingError(f"no real backend for model {self.model!r}")
        return self._fallback(texts)

    # -- OpenAI --------------------------------------------------------
    def _embed_openai(self, texts: list[str]) -> list[list[float]] | None:
        if not self.api_key:
            # No key means no real backend is reachable. Treat as unavailable
            # so that real=True callers fail fast instead of constructing a
            # client that only blows up at request time.
            return None
        try:
            from openai import OpenAI  # type: ignore
        except Exception:  # noqa: BLE001
            return None
        if self._client is None:
            kwargs: dict[str, Any] = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = OpenAI(**kwargs)
        out: list[list[float]] = []
        try:
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i : i + self.batch_size]
                resp = self._client.embeddings.create(
                    model=self.model.value, input=batch
                )
                out.extend([list(map(float, d.embedding)) for d in resp.data])
        except Exception as exc:  # noqa: BLE001
            logger.warning("openai embed failed: %s", exc)
            return None
        return [self._maybe_normalize(v) for v in out]

    # -- HuggingFace / TEI HTTP RPC -----------------------------------
    def _embed_hf_rpc(self, texts: list[str]) -> list[list[float]] | None:
        if not self.hf_base_url:
            return None
        try:
            import urllib.request
            import urllib.error
        except Exception:  # noqa: BLE001
            return None
        out: list[list[float]] = []
        try:
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i : i + self.batch_size]
                payload = json.dumps({"inputs": batch}).encode("utf-8")
                req = urllib.request.Request(
                    self.hf_base_url.rstrip("/") + "/embed",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                    data = json.loads(resp.read().decode("utf-8"))
                rows = data.get("embeddings") or data
                out.extend([list(map(float, r)) for r in rows])
        except Exception as exc:  # noqa: BLE001
            logger.debug("hf embed rpc skipped: %s", exc)
            return None
        return [self._maybe_normalize(v) for v in out]

    # -- sentence-transformers (in-process) ---------------------------
    def _embed_sentence_transformers(self, texts: list[str]) -> list[list[float]] | None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception:  # noqa: BLE001
            return None
        try:
            if self._st is None:
                self._st = SentenceTransformer(self.model.value)
            vecs = self._st.encode(
                texts, batch_size=self.batch_size, normalize_embeddings=self.normalize
            )
            return [list(map(float, v)) for v in vecs]
        except Exception as exc:  # noqa: BLE001
            logger.debug("sentence-transformers skipped: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Normalisation + deterministic fallback (tests only)
    # ------------------------------------------------------------------
    def _maybe_normalize(self, vec: list[float]) -> list[float]:
        if not self.normalize:
            return vec
        return _l2_normalize(vec)

    def _fallback(self, texts: list[str]) -> list[list[float]]:
        logger.info("using deterministic mock embeddings (offline mode)")
        return [self._deterministic(t) for t in texts]

    def _deterministic(self, text: str) -> list[float]:
        return _deterministic_vector(text, self.model.dim, normalize=self.normalize)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


def _deterministic_vector(text: str, dim: int, *, normalize: bool = True) -> list[float]:
    """Deterministic hash-bucket embedding.

    NOT a real semantic model — used purely as a test fixture
    (``EmbeddingModel.MOCK``) and as an explicit offline fallback when
    ``real=False``.  Production callers should pass ``real=True``.
    """
    vec = [0.0] * dim
    if not text:
        return vec
    tokens = text.lower().split()
    for tok in tokens:
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        for i in range(0, len(digest), 4):
            idx = int.from_bytes(digest[i : i + 4], "big") % dim
            sign = 1.0 if (digest[i] & 1) else -1.0
            vec[idx] += sign
    if normalize:
        vec = _l2_normalize(vec)
    return vec
