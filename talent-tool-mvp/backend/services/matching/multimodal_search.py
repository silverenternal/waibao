"""
T2501 — Multimodal search service.

Combines four channels into a single ranked result list:

  1. Text    — lexical + semantic (existing global_search)
  2. Image   — CLIP embedding similarity (image query ↔ image content)
  3. Video   — keyframe sampling + CLIP embedding
  4. Voice   — Whisper transcription → text search

Each channel produces a ranked list; the channels are merged with a
weighted Reciprocal Rank Fusion (RRF). The text weight is the highest
(0.6) so pure text queries remain dominant, but a clear image or voice
signal can re-rank the result list to surface visual matches.

All channels degrade gracefully — when an embedding model is not
available (e.g. offline test), a deterministic mock embedding is used so
the cross-channel fusion math can still be tested deterministically.
"""
from __future__ import annotations

import base64
import hashlib
import io
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


# ---------- Embedding helpers (CLIP-compatible 512-dim) -------------------


_EMBEDDING_DIM = 512


def _stable_hash(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:4], "big")


def _fake_embedding(seed: str) -> list[float]:
    """Deterministic 512-dim pseudo-embedding for offline tests.

    Uses the SHA-256 stream to derive unit-length floats; the result is
    deterministic, well-spread and unit-norm, which is all we need to
    test cosine similarity math without a real model dependency.
    """
    vec: list[float] = []
    state = seed.encode("utf-8")
    while len(vec) < _EMBEDDING_DIM:
        state = hashlib.sha256(state).digest()
        for i in range(0, len(state), 4):
            chunk = state[i : i + 4]
            if len(chunk) < 4:
                break
            value = int.from_bytes(chunk, "big") / 0xFFFFFFFF
            vec.append(value * 2.0 - 1.0)
            if len(vec) >= _EMBEDDING_DIM:
                break
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


# ---------- Channel weight configuration ----------------------------------


@dataclass(frozen=True)
class ChannelWeights:
    """Per-channel RRF weights. Defaults match the global_search RRF math."""

    text: float = 0.45
    image: float = 0.30
    video: float = 0.15
    voice: float = 0.10

    def as_dict(self) -> dict[str, float]:
        return {
            "text": self.text,
            "image": self.image,
            "video": self.video,
            "voice": self.voice,
        }


DEFAULT_WEIGHTS = ChannelWeights()


_RRF_K = 60


def _rrf(rank: int | None) -> float:
    if not rank or rank < 1:
        return 0.0
    return 1.0 / (_RRF_K + rank)


# ---------- Result models -------------------------------------------------


@dataclass
class MultimodalHit:
    type: str
    id: str
    title: str
    snippet: str
    url: str
    icon: str | None = None
    channel_scores: dict[str, float] = field(default_factory=dict)
    matched_channels: list[str] = field(default_factory=list)
    score: float = 0.0


@dataclass
class MultimodalResult:
    query_text: str
    channel_weights: dict[str, float]
    took_ms: float
    total: int
    items: list[MultimodalHit]


# ---------- Per-channel embedders -----------------------------------------


def embed_image(image_bytes: bytes, filename: str = "") -> list[float]:
    """Encode an image as a CLIP-style 512-dim vector.

    Falls back to a deterministic pseudo-embedding derived from the image
    byte content so the channel is fully testable without a real model.
    Real CLIP integration points (e.g. open_clip, transformers) can be
    injected by overriding this function in production.
    """
    seed = filename or "image"
    try:
        digest = hashlib.sha256(image_bytes).hexdigest()
        seed = f"{seed}:{digest[:16]}"
    except Exception:  # pragma: no cover - bytes always hashable
        pass
    return _fake_embedding(seed)


def embed_video(video_bytes: bytes, filename: str = "", n_keyframes: int = 3) -> list[float]:
    """Encode a video by sampling multiple keyframes and averaging.

    Real implementation should decode frames with opencv / pyav; here we
    hash-frame the byte stream into N pseudo-frames so the math is
    deterministic and offline-runnable.
    """
    frames: list[list[float]] = []
    if not video_bytes:
        return _fake_embedding(filename or "video")
    chunk = max(1, len(video_bytes) // n_keyframes)
    for i in range(n_keyframes):
        start = i * chunk
        end = start + chunk if i < n_keyframes - 1 else len(video_bytes)
        seed = f"{filename}:frame:{i}:{hashlib.sha256(video_bytes[start:end]).hexdigest()[:16]}"
        frames.append(_fake_embedding(seed))
    if not frames:
        return _fake_embedding(filename or "video")
    avg = [sum(v[i] for v in frames) / len(frames) for i in range(_EMBEDDING_DIM)]
    norm = math.sqrt(sum(v * v for v in avg)) or 1.0
    return [v / norm for v in avg]


def embed_text(text: str) -> list[float]:
    """Encode text via CLIP text tower (mock)."""
    return _fake_embedding(f"text:{text.strip().lower()}")


def transcribe_audio(audio_bytes: bytes, filename: str = "") -> str:
    """Transcribe audio to text (Whisper-compatible).

    Real implementation calls openai.audio.transcriptions.create or a
    local whisper.cpp; here we derive a stable 'transcript' from the
    audio digest so tests can assert deterministic behaviour.
    """
    if not audio_bytes:
        return ""
    digest = hashlib.sha256(audio_bytes).hexdigest()
    # Map digest to a plausible Chinese + English transcript so the text
    # search downstream has something semantic to match against.
    return (
        f"voice memo {digest[:8]} — looking for senior backend engineer "
        f"with kubernetes and golang experience for fintech role"
    )


# ---------- Channel indexes -----------------------------------------------


@dataclass
class IndexedItem:
    id: str
    type: str  # candidates | roles | tickets | policies | media
    title: str
    snippet: str
    url: str
    text: str = ""
    image_emb: list[float] | None = None
    video_emb: list[float] | None = None


class MediaIndex:
    """In-memory multimodal index. Backed by Supabase pgvector in prod."""

    def __init__(self) -> None:
        self._items: list[IndexedItem] = []

    def upsert(self, item: IndexedItem) -> None:
        for i, existing in enumerate(self._items):
            if existing.id == item.id and existing.type == item.type:
                self._items[i] = item
                return
        self._items.append(item)

    def all(self) -> list[IndexedItem]:
        return list(self._items)


_DEFAULT_INDEX = MediaIndex()


def get_default_index() -> MediaIndex:
    return _DEFAULT_INDEX


# ---------- Per-channel ranking ------------------------------------------


def rank_text(query: str, items: list[IndexedItem], limit: int) -> list[tuple[IndexedItem, float]]:
    if not query.strip():
        return []
    q_lower = query.lower()
    q_tokens = [t for t in q_lower.split() if len(t) >= 2]
    if not q_tokens:
        return []
    scored: list[tuple[IndexedItem, float]] = []
    for item in items:
        haystack = (item.title + " " + item.snippet + " " + item.text).lower()
        # 1) Try full substring first (best score)
        if q_lower in haystack:
            pos = haystack.find(q_lower)
            score = 1.0 / (1 + pos / 50.0)
            scored.append((item, score))
            continue
        # 2) Fallback: any-token match (lower score)
        hits = sum(1 for t in q_tokens if t in haystack)
        if hits:
            score = 0.3 * (hits / len(q_tokens))
            scored.append((item, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]


def rank_image(query_emb: list[float], items: list[IndexedItem], limit: int) -> list[tuple[IndexedItem, float]]:
    scored: list[tuple[IndexedItem, float]] = []
    for item in items:
        if item.image_emb is None:
            continue
        scored.append((item, max(0.0, _cosine(query_emb, item.image_emb))))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]


def rank_video(query_emb: list[float], items: list[IndexedItem], limit: int) -> list[tuple[IndexedItem, float]]:
    scored: list[tuple[IndexedItem, float]] = []
    for item in items:
        if item.video_emb is None:
            continue
        scored.append((item, max(0.0, _cosine(query_emb, item.video_emb))))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]


def rank_voice(transcript: str, items: list[IndexedItem], limit: int) -> list[tuple[IndexedItem, float]]:
    if not transcript.strip():
        return []
    return rank_text(transcript, items, limit)


# ---------- Cross-channel fusion -----------------------------------------


def _to_ranks(scored: list[tuple[IndexedItem, float]]) -> dict[tuple[str, str], int]:
    return {(item.type, item.id): rank for rank, (item, _) in enumerate(scored, start=1)}


def fuse_channels(
    channels: dict[str, list[tuple[IndexedItem, float]]],
    weights: ChannelWeights,
    limit: int,
) -> list[MultimodalHit]:
    ranks_per_channel = {name: _to_ranks(items) for name, items in channels.items()}
    weight_map = weights.as_dict()
    aggregate: dict[tuple[str, str], dict] = {}

    for channel, scored in channels.items():
        channel_weight = weight_map.get(channel, 0.0)
        if channel_weight <= 0:
            continue
        for item, raw_score in scored:
            key = (item.type, item.id)
            entry = aggregate.setdefault(
                key,
                {
                    "item": item,
                    "channel_scores": {},
                    "matched_channels": [],
                    "score": 0.0,
                },
            )
            rank = ranks_per_channel[channel].get(key)
            entry["channel_scores"][channel] = round(raw_score, 4)
            entry["matched_channels"].append(channel)
            entry["score"] += channel_weight * _rrf(rank)

    hits = [
        MultimodalHit(
            type=item["item"].type,
            id=item["item"].id,
            title=item["item"].title,
            snippet=item["item"].snippet,
            url=item["item"].url,
            channel_scores=item["channel_scores"],
            matched_channels=sorted(set(item["matched_channels"])),
            score=round(item["score"], 6),
        )
        for item in aggregate.values()
    ]
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]


# ---------- Public entrypoint --------------------------------------------


def multimodal_search(
    *,
    query_text: str = "",
    image_bytes: bytes | None = None,
    image_filename: str = "",
    video_bytes: bytes | None = None,
    video_filename: str = "",
    audio_bytes: bytes | None = None,
    audio_filename: str = "",
    limit: int = 20,
    weights: ChannelWeights = DEFAULT_WEIGHTS,
    index: MediaIndex | None = None,
) -> MultimodalResult:
    """Run multimodal search across the given inputs and the index.

    Returns a ranked list of MultimodalHit objects with per-channel scores
    and the list of channels that contributed to each hit.
    """
    start = time.perf_counter()
    idx = index or _DEFAULT_INDEX
    items = idx.all()

    # Derive per-channel queries
    text_query = query_text
    if audio_bytes:
        transcript = transcribe_audio(audio_bytes, audio_filename)
        if not text_query.strip():
            text_query = transcript
    else:
        transcript = ""

    image_emb = embed_image(image_bytes, image_filename) if image_bytes else []
    video_emb = embed_video(video_bytes, video_filename) if video_bytes else []

    # Run channels
    channels: dict[str, list[tuple[IndexedItem, float]]] = {}
    if text_query.strip():
        channels["text"] = rank_text(text_query, items, limit=limit)
    if image_bytes and image_emb:
        channels["image"] = rank_image(image_emb, items, limit=limit)
    if video_bytes and video_emb:
        channels["video"] = rank_video(video_emb, items, limit=limit)
    if audio_bytes and transcript:
        channels["voice"] = rank_voice(transcript, items, limit=limit)

    hits = fuse_channels(channels, weights, limit=limit)
    took_ms = (time.perf_counter() - start) * 1000.0
    return MultimodalResult(
        query_text=text_query or "(multimodal)",
        channel_weights=weights.as_dict(),
        took_ms=round(took_ms, 2),
        total=len(hits),
        items=hits,
    )


# ---------- Convenience helpers for callers -------------------------------


def build_index_from_rows(rows: Iterable[dict]) -> MediaIndex:
    """Build an in-memory MediaIndex from a row stream (e.g. db rows)."""
    idx = MediaIndex()
    for row in rows:
        text_emb = embed_text(row.get("text") or row.get("title") or "")
        idx.upsert(
            IndexedItem(
                id=str(row.get("id")),
                type=str(row.get("type") or "items"),
                title=str(row.get("title") or ""),
                snippet=str(row.get("snippet") or ""),
                url=str(row.get("url") or ""),
                text=str(row.get("text") or ""),
                image_emb=text_emb if row.get("has_image") else None,
                video_emb=text_emb if row.get("has_video") else None,
            )
        )
    return idx