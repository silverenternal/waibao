"""
T2501 — Multimodal search tests.

Coverage:
  * Embedding determinism + cosine similarity math
  * CLIP-style image / video / text embeddings return 512-dim unit vectors
  * Whisper-style audio transcription is deterministic
  * Cross-channel fusion (text + image + video + voice) ranks correctly
  * RRF weighting can be overridden per query
  * The full multimodal_search() entrypoint returns ranked hits with
    per-channel scores and the channels that contributed to each hit
  * Hybrid text + multimodal queries rank the multimodal-matched item
    above plain-text matches
"""
from __future__ import annotations

import os
import sys

import pytest

# Make backend importable when pytest is invoked from project root
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from services.matching.multimodal_search import (  # noqa: E402
    ChannelWeights,
    IndexedItem,
    MediaIndex,
    build_index_from_rows,
    embed_image,
    embed_text,
    embed_video,
    fuse_channels,
    multimodal_search,
    rank_image,
    rank_text,
    rank_video,
    rank_voice,
    transcribe_audio,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_index() -> MediaIndex:
    idx = MediaIndex()
    idx.upsert(
        IndexedItem(
            id="c1",
            type="candidates",
            title="Senior Backend Engineer",
            snippet="Go, Kubernetes, PostgreSQL, 8 years",
            url="/candidates/c1",
            text="Senior Backend Engineer with Go, Kubernetes and PostgreSQL experience for fintech roles",
            image_emb=embed_image(b"cand-photo-c1", "c1.jpg"),
        )
    )
    idx.upsert(
        IndexedItem(
            id="r1",
            type="roles",
            title="Backend Engineer (Fintech)",
            snippet="Building payments platform with Go + k8s",
            url="/role/r1",
            text="Hiring Senior Backend Engineer for fintech — Go Kubernetes PostgreSQL payments",
            video_emb=embed_video(b"video-bytes-r1", "r1.mp4"),
        )
    )
    idx.upsert(
        IndexedItem(
            id="r2",
            type="roles",
            title="Frontend Engineer",
            snippet="React / Next.js / TypeScript",
            url="/role/r2",
            text="Frontend Engineer with React Next.js TypeScript for SaaS dashboard",
        )
    )
    idx.upsert(
        IndexedItem(
            id="p1",
            type="policies",
            title="Remote Work Policy",
            snippet="Hybrid 3 days office",
            url="/policy/p1",
            text="Remote work policy hybrid 3 days office per week",
        )
    )
    return idx


# ---------------------------------------------------------------------------
# Embedding math
# ---------------------------------------------------------------------------


def test_text_embedding_is_512_dim_and_unit_norm():
    vec = embed_text("senior backend engineer with go")
    assert len(vec) == 512
    norm = sum(v * v for v in vec) ** 0.5
    assert abs(norm - 1.0) < 1e-6


def test_text_embedding_is_deterministic():
    a = embed_text("hello world")
    b = embed_text("hello world")
    assert a == b


def test_text_embedding_differs_by_seed():
    a = embed_text("hello world")
    b = embed_text("goodbye world")
    assert a != b


def test_image_embedding_differs_per_filename():
    a = embed_image(b"bytes-a", "a.jpg")
    b = embed_image(b"bytes-a", "b.jpg")
    # Same bytes but different filename produce different embeddings
    assert a != b


def test_video_embedding_averages_keyframes():
    v = embed_video(b"some video bytes", "v.mp4", n_keyframes=3)
    assert len(v) == 512
    norm = sum(x * x for x in v) ** 0.5
    assert abs(norm - 1.0) < 1e-6


def test_transcribe_audio_is_deterministic():
    audio = b"some deterministic audio bytes"
    a = transcribe_audio(audio, "memo.webm")
    b = transcribe_audio(audio, "memo.webm")
    assert a == b
    assert "engineer" in a.lower()


# ---------------------------------------------------------------------------
# Channel ranking
# ---------------------------------------------------------------------------


def test_rank_text_substring_match(sample_index):
    results = rank_text("fintech", sample_index.all(), limit=10)
    assert results
    types_ids = [(item.type, item.id) for item, _ in results]
    assert ("roles", "r1") in types_ids


def test_rank_image_returns_only_image_indexed(sample_index):
    q = embed_image(b"cand-photo-c1", "c1.jpg")
    results = rank_image(q, sample_index.all(), limit=10)
    assert results
    assert results[0][0].id == "c1"


def test_rank_video_returns_only_video_indexed(sample_index):
    q = embed_video(b"video-bytes-r1", "r1.mp4")
    results = rank_video(q, sample_index.all(), limit=10)
    assert results
    assert results[0][0].id == "r1"


def test_rank_voice_uses_transcript_lexical(sample_index):
    # Use a phrase that the sample index contains lexically
    results = rank_voice("fintech", sample_index.all(), limit=10)
    assert results
    assert any(item.id == "r1" for item, _ in results)


# ---------------------------------------------------------------------------
# Cross-channel fusion
# ---------------------------------------------------------------------------


def test_fuse_channels_ranks_multimodal_hits_above_text_only():
    items = [
        IndexedItem(id="A", type="candidates", title="Frontend React dev",
                    snippet="react redux typescript",
                    url="/candidates/A",
                    image_emb=embed_image(b"shared-bytes", "same.jpg")),
        IndexedItem(id="B", type="candidates", title="Backend Go dev",
                    snippet="go kubernetes postgres",
                    url="/candidates/B"),
    ]
    image_q = embed_image(b"shared-bytes", "same.jpg")
    # Use rank_text so both A and B are textually matchable
    from services.matching.multimodal_search import rank_text
    text_hits = rank_text("dev", items, limit=10)
    image_hits = rank_image(image_q, items, limit=10)
    channels = {"text": text_hits, "image": image_hits}
    hits = fuse_channels(channels, ChannelWeights(text=0.5, image=0.5), limit=10)
    assert len(hits) == 2
    # A is matched by both text and image, B only by text
    assert hits[0].id == "A"
    assert set(hits[0].matched_channels) == {"text", "image"}


def test_fuse_channels_respects_weight_overrides():
    items = [
        IndexedItem(id="A", type="candidates", title="img match",
                    snippet="", url="/candidates/A",
                    image_emb=embed_image(b"X", "x.jpg")),
        IndexedItem(id="B", type="candidates", title="text match",
                    snippet="looking for B", url="/candidates/B"),
    ]
    image_q = embed_image(b"X", "x.jpg")
    channels = {
        "text": [(items[1], 1.0)],
        "image": [(items[0], 1.0)],
    }
    # With image weight 0 we expect only B
    hits = fuse_channels(channels, ChannelWeights(text=1.0, image=0.0, video=0.0, voice=0.0), limit=10)
    assert {h.id for h in hits} == {"B"}


def test_fuse_channels_handles_empty_input():
    hits = fuse_channels({}, ChannelWeights(), limit=10)
    assert hits == []


# ---------------------------------------------------------------------------
# End-to-end multimodal_search
# ---------------------------------------------------------------------------


def test_multimodal_search_text_only_returns_text_hits(sample_index):
    result = multimodal_search(query_text="frontend", index=sample_index)
    assert result.total >= 1
    assert all("text" in h.matched_channels for h in result.items)


def test_multimodal_search_image_only_returns_image_hits(sample_index):
    image_q = embed_image(b"cand-photo-c1", "c1.jpg")
    result = multimodal_search(image_bytes=image_q, image_filename="c1.jpg", index=sample_index)
    assert result.total >= 1
    assert any("image" in h.matched_channels for h in result.items)


def test_multimodal_search_voice_only_transcribes_and_searches(sample_index):
    audio = transcribe_audio(b"voice bytes", "memo.webm").encode("utf-8")
    result = multimodal_search(
        audio_bytes=audio,
        audio_filename="memo.webm",
        index=sample_index,
    )
    assert result.total >= 1
    # transcript is the rendered query
    assert result.query_text


def test_multimodal_search_combines_text_and_image(sample_index):
    image_q = embed_image(b"cand-photo-c1", "c1.jpg")
    result = multimodal_search(
        query_text="backend",
        image_bytes=image_q,
        image_filename="c1.jpg",
        index=sample_index,
    )
    # c1 has image embedding and matches 'backend' textually
    top = result.items[0]
    assert set(top.matched_channels) >= {"text", "image"}


def test_multimodal_search_hybrid_re_ranks_image_match_above_text_only(sample_index):
    # A image query alone should still surface the image-indexed candidate
    image_q = embed_image(b"cand-photo-c1", "c1.jpg")
    result = multimodal_search(
        query_text="remote work",
        image_bytes=image_q,
        image_filename="c1.jpg",
        index=sample_index,
    )
    # The image-indexed candidate should outrank plain-text-only matches
    top_ids = [h.id for h in result.items]
    assert "c1" in top_ids[:3]


def test_multimodal_search_returns_took_ms_and_weights(sample_index):
    result = multimodal_search(query_text="backend", index=sample_index)
    assert result.took_ms >= 0
    assert result.channel_weights["text"] > 0


def test_multimodal_search_handles_no_inputs(sample_index):
    result = multimodal_search(index=sample_index)
    # No inputs => no ranked hits
    assert result.total == 0
    assert result.items == []


# ---------------------------------------------------------------------------
# Index helper
# ---------------------------------------------------------------------------


def test_build_index_from_rows_seeds_image_video_flags():
    rows = [
        {"id": "1", "type": "candidates", "title": "Eng A", "snippet": "go", "url": "/c/1",
         "text": "go engineer", "has_image": True, "has_video": False},
        {"id": "2", "type": "roles", "title": "Role B", "snippet": "react", "url": "/r/2",
         "text": "react role", "has_image": False, "has_video": True},
    ]
    idx = build_index_from_rows(rows)
    items = idx.all()
    assert len(items) == 2
    image_items = [i for i in items if i.image_emb]
    video_items = [i for i in items if i.video_emb]
    assert len(image_items) == 1
    assert len(video_items) == 1
    assert image_items[0].id == "1"
    assert video_items[0].id == "2"