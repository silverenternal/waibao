"""Realtime v2 API (T2201) — OpenAI GPT-4o Realtime integration.

Endpoints
---------
- POST   /api/realtime/sessions              create a session, return token + ws_url
- GET    /api/realtime/sessions              list current user's sessions
- GET    /api/realtime/sessions/{id}         session details + transcript + metrics
- DELETE /api/realtime/sessions/{id}         stop + remove a session
- WS     /api/realtime/ws/{session_id}       bidirectional audio/text stream

Wire protocol (client ↔ server, JSON):

    client -> server:
        {"type": "audio", "data": "<base64 PCM16>"}
        {"type": "text",  "text": "..."}
        {"type": "interrupt"}
        {"type": "stop"}

    server -> client:
        {"type": "ready", "session_id": "...", "model": "...", "voice": "..."}
        {"type": "vad_speech_start"}
        {"type": "vad_speech_stop"}
        {"type": "audio_committed"}
        {"type": "text_delta", "delta": "..."}
        {"type": "text_done",  "text": "..."}
        {"type": "audio_delta","audio": "<base64>"}
        {"type": "response_done", "usage": {...}}
        {"type": "function_call", "name": "...", "arguments": {...}}
        {"type": "user_text", "text": "..."}
        {"type": "interrupted"}
        {"type": "error", "message": "..."}
        {"type": "closed"}
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from providers.llm.openai_realtime import (
    DEFAULT_REALTIME_MODEL,
    DEFAULT_VOICE,
    RealtimeSessionConfig,
)
from services.platform.realtime_session import (
    RealtimeSession,
    make_session_id,
    persist_metrics,
    persist_session_row,
    persist_transcript,
    registry as session_registry,
)

logger = logging.getLogger("recruittech.api.realtime_v2")
router = APIRouter()

# ---------------------------------------------------------------------------
# In-memory mirrors of Supabase tables
# ---------------------------------------------------------------------------
_SESSIONS: dict[str, dict[str, Any]] = {}
_TRANSCRIPTS: dict[str, list[dict[str, Any]]] = {}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class CreateSessionBody(BaseModel):
    conversation_id: str = Field(default_factory=lambda: f"conv_{uuid.uuid4().hex[:10]}")
    model: str = DEFAULT_REALTIME_MODEL
    voice: str = DEFAULT_VOICE
    instructions: Optional[str] = None
    modalities: list[str] = Field(default_factory=lambda: ["audio", "text"])
    input_audio_format: str = "pcm16"
    output_audio_format: str = "pcm16"
    temperature: float = 0.7
    tools: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    force_mock: bool = False


# ---------------------------------------------------------------------------
# POST /sessions
# ---------------------------------------------------------------------------
@router.post("/sessions", summary="创建 Realtime 会话")
async def create_session(
    body: CreateSessionBody,
    user: CurrentUser = Depends(get_current_user),
):
    session_id = make_session_id()
    config = RealtimeSessionConfig(
        model=body.model,
        voice=body.voice,
        instructions=body.instructions or RealtimeSessionConfig().instructions,
        modalities=body.modalities or ["audio", "text"],
        input_audio_format=body.input_audio_format,
        output_audio_format=body.output_audio_format,
        temperature=body.temperature,
        tools=body.tools,
        metadata={**body.metadata, "user_id": str(user.id), "conversation_id": body.conversation_id},
    )
    row = {
        "id": session_id,
        "user_id": str(user.id),
        "conversation_id": body.conversation_id,
        "model": body.model,
        "voice": body.voice,
        "status": "created",
        "created_at": _now(),
        "metadata": json.dumps(body.metadata or {}, ensure_ascii=False),
    }
    _SESSIONS[session_id] = row
    _TRANSCRIPTS[session_id] = []
    await persist_session_row(row)

    return {
        "id": session_id,
        "user_id": str(user.id),
        "conversation_id": body.conversation_id,
        "model": body.model,
        "voice": body.voice,
        "status": "created",
        "ws_path": f"/api/realtime-v2/ws/{session_id}",
        "created_at": row["created_at"],
        "config": config.to_session_update(),
    }


# ---------------------------------------------------------------------------
# GET /sessions
# ---------------------------------------------------------------------------
@router.get("/sessions", summary="列出当前用户的 Realtime 会话")
async def list_sessions(user: CurrentUser = Depends(get_current_user)):
    items = [s for s in _SESSIONS.values() if s.get("user_id") == str(user.id)]
    items.sort(key=lambda s: s.get("created_at", ""), reverse=True)
    return {"items": items, "count": len(items)}


# ---------------------------------------------------------------------------
# GET /sessions/{id}
# ---------------------------------------------------------------------------
@router.get("/sessions/{session_id}", summary="查看会话详情 + 转写 + 指标")
async def get_session(
    session_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    row = _SESSIONS.get(session_id)
    if not row or row.get("user_id") != str(user.id):
        raise HTTPException(status_code=404, detail="session not found")
    active = session_registry.get(session_id)
    return {
        **row,
        "transcript": _TRANSCRIPTS.get(session_id, []),
        "metrics": active.metrics.to_dict() if active else None,
        "is_active": active is not None,
    }


# ---------------------------------------------------------------------------
# DELETE /sessions/{id}
# ---------------------------------------------------------------------------
@router.delete("/sessions/{session_id}", summary="停止并删除会话")
async def delete_session(
    session_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    row = _SESSIONS.get(session_id)
    if not row or row.get("user_id") != str(user.id):
        raise HTTPException(status_code=404, detail="session not found")
    active = session_registry.get(session_id)
    if active:
        await session_registry.unregister(session_id)
        await active.stop()
        try:
            await persist_metrics(session_id, active.metrics.to_dict())
        except Exception:  # noqa: BLE001
            pass
    row["status"] = "ended"
    row["ended_at"] = _now()
    _SESSIONS[session_id] = row
    await persist_session_row(row)
    return {"ok": True, "id": session_id, "status": "ended"}


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------
@router.websocket("/ws/{session_id}")
async def ws_realtime(
    websocket: WebSocket,
    session_id: str,
    token: Optional[str] = Query(default=None),
):
    """Bidirectional Realtime bridge.

    First message must carry auth: ``{"type": "hello", "token": "<jwt>"}``,
    or pass ``?token=...`` as a query parameter.
    """
    await websocket.accept()
    # Auth: token from query or first hello
    auth_token = token
    if not auth_token:
        try:
            first = await asyncio.wait_for(websocket.receive_text(), timeout=5)
            msg = json.loads(first)
            if msg.get("type") != "hello":
                await websocket.send_json({"type": "error", "message": "expected hello"})
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            auth_token = msg.get("token", "")
        except Exception:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    if not auth_token:
        await websocket.send_json({"type": "error", "message": "missing token"})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    # Allow a "dev:" prefix for local development / tests
    if auth_token.startswith("dev:"):
        user_id = auth_token.split(":", 1)[1] or "dev-user"
        payload = {"sub": user_id, "user_metadata": {"role": "jobseeker"}}
    else:
        try:
            from api.auth import decode_supabase_jwt
            payload = decode_supabase_jwt(auth_token)
            user_id = payload.get("sub", "anonymous")
        except Exception:  # noqa: BLE001
            await websocket.send_json({"type": "error", "message": "invalid token"})
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    row = _SESSIONS.get(session_id)
    if not row or row.get("user_id") != user_id:
        await websocket.send_json({"type": "error", "message": "session not found"})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    config = RealtimeSessionConfig(
        model=row.get("model") or DEFAULT_REALTIME_MODEL,
        voice=row.get("voice") or DEFAULT_VOICE,
    )

    async def dispatch(payload: dict[str, Any]) -> None:
        # Persist transcript turns
        if payload.get("type") == "text_done":
            txt = payload.get("text") or ""
            if txt:
                turn = {
                    "role": "assistant",
                    "text": txt,
                    "ts": payload.get("ts", time.time()),
                }
                _TRANSCRIPTS.setdefault(session_id, []).append(turn)
                try:
                    await persist_transcript(session_id, turn)
                except Exception:  # noqa: BLE001
                    pass
        elif payload.get("type") == "user_text":
            txt = payload.get("text") or ""
            if txt:
                turn = {
                    "role": "user",
                    "text": txt,
                    "ts": payload.get("ts", time.time()),
                }
                _TRANSCRIPTS.setdefault(session_id, []).append(turn)
                try:
                    await persist_transcript(session_id, turn)
                except Exception:  # noqa: BLE001
                    pass
        await websocket.send_json(payload)

    # Default agent bridge: simple echo+summary using get_llm_provider if available
    async def agent_bridge(name: str, args: dict[str, Any], ctx: dict[str, Any]) -> str:
        try:
            from providers.registry import get_llm_provider
            llm = get_llm_provider()
            from providers.llm.base import Message
            resp = await llm.chat(
                messages=[Message(role="user", content=f"Tool {name} called with: {args}. Reply concisely.")],
                temperature=0.3,
                max_tokens=200,
            )
            return resp.content or "(no result)"
        except Exception as e:  # noqa: BLE001
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    session = RealtimeSession(
        session_id=session_id,
        user_id=user_id,
        conversation_id=row.get("conversation_id", ""),
        config=config,
        agent_bridge=agent_bridge,
        dispatch=dispatch,
        force_mock=not bool(os.environ.get("OPENAI_API_KEY")),
    )
    await session_registry.register(session)
    row["status"] = "active"
    await persist_session_row(row)

    await websocket.send_json(
        {"type": "connected", "session_id": session_id, "user_id": user_id}
    )

    await session.start()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "invalid json"})
                continue
            mtype = msg.get("type")
            if mtype == "audio":
                data = msg.get("data") or ""
                await session.push_audio(data)
            elif mtype == "text":
                await session.push_text(msg.get("text", ""))
            elif mtype == "interrupt":
                await session.interrupt()
            elif mtype == "stop":
                await session.stop()
                await websocket.send_json({"type": "closed"})
                break
            elif mtype == "ping":
                await websocket.send_json({"type": "pong", "ts": msg.get("ts", time.time())})
            else:
                await websocket.send_json({"type": "error", "message": f"unknown type: {mtype}"})
    except WebSocketDisconnect:
        logger.info("Realtime WS client disconnected: %s", session_id)
    except Exception as e:  # noqa: BLE001
        logger.exception("Realtime WS error: %s", e)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:  # noqa: BLE001
            pass
    finally:
        try:
            metrics = session.metrics.to_dict()
            row["status"] = "ended"
            row["ended_at"] = _now()
            _SESSIONS[session_id] = row
            await persist_session_row(row)
            await persist_metrics(session_id, metrics)
        except Exception:  # noqa: BLE001
            pass
        await session.stop()
        await session_registry.unregister(session_id)
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass
