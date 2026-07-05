"""Realtime API — WebSocket 端点 + SSE.

支持求职者/用人方任意时刻召唤智能体,秒级路由与响应.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from agents.registry import registry
from agents.runtime import AgentInput
from api.auth import CurrentUser, get_current_user
from services.realtime_router import RealtimeRouter

logger = logging.getLogger("recruittech.api.realtime")
router = APIRouter()

# 全局 router 单例
_rt_router: Optional[RealtimeRouter] = None


def get_router() -> RealtimeRouter:
    global _rt_router
    if _rt_router is None:
        _rt_router = RealtimeRouter(registry=registry)
    return _rt_router


# ---- HTTP: 触发一次 agent 调用(供非 WS 客户端使用) ----

class InvokeRequest(BaseModel):
    agent_name: str = ""                              # 空则自动路由
    text: str
    context: dict = {}
    stream: bool = True


@router.post("/invoke")
async def invoke_agent(
    body: InvokeRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """召唤智能体,根据用户输入自动选择 agent 或使用指定 agent."""
    rt = get_router()
    agent_input = AgentInput(
        user_id=str(user.id),
        persona=user.role.value,
        text=body.text,
        context=body.context,
    )
    agent_name = body.agent_name or rt.route(body.text, persona=user.role.value)
    agent = registry.get_or_raise(agent_name)

    output = await agent.run(agent_input)
    return {
        "agent": agent_name,
        "text": output.text,
        "artifacts": output.artifacts,
        "success": output.success,
        "cost_cents": output.cost_cents,
        "request_id": output.request_id,
    }


# ---- WebSocket ----

@router.websocket("/ws/invoke")
async def ws_invoke(
    websocket: WebSocket,
    token: Optional[str] = Query(default=None),
):
    """WebSocket 端点: 双向流式对话.

    客户端发送:
        {"text": "...", "agent_name": "可选", "context": {...}}

    服务端推送:
        {"type": "start", "agent": "...", "request_id": "..."}
        {"type": "chunk", "text": "..."}
        {"type": "tool_call", "tool": "...", "args": {...}}
        {"type": "done", "artifacts": {...}, "cost_cents": 0}
        {"type": "error", "message": "..."}
    """
    await websocket.accept()
    rt = get_router()
    request_id = str(uuid.uuid4())[:12]

    try:
        # 简化认证: token 通过 query 传入,生产应改为首次消息携带 JWT
        if not token:
            await websocket.send_json({"type": "error", "message": "missing token"})
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # 解码 token (简化,生产用 decode_supabase_jwt)
        from api.auth import decode_supabase_jwt
        payload = decode_supabase_jwt(token)
        user_id = payload.get("sub", "anonymous")
        persona = payload.get("user_metadata", {}).get("role", "jobseeker")

        await websocket.send_json({
            "type": "ready",
            "user_id": user_id,
            "persona": persona,
        })

        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "invalid json"})
                continue

            text = msg.get("text", "")
            explicit_agent = msg.get("agent_name", "")
            ctx = msg.get("context", {})
            agent_name = explicit_agent or rt.route(text, persona=persona)
            agent = registry.get(agent_name)

            if agent is None:
                await websocket.send_json({"type": "error", "message": f"agent {agent_name} not found"})
                continue

            await websocket.send_json({"type": "start", "agent": agent_name, "request_id": request_id})

            # 流式调用 (MVP: 一次性返回; 未来用 OpenAI stream)
            input_obj = AgentInput(
                user_id=user_id,
                persona=persona,
                text=text,
                context=ctx,
            )
            output = await agent.run(input_obj)

            # 模拟 chunk 流式输出
            chunk_size = 20
            for i in range(0, len(output.text), chunk_size):
                await websocket.send_json({
                    "type": "chunk",
                    "text": output.text[i:i+chunk_size],
                })
                await asyncio.sleep(0.02)

            await websocket.send_json({
                "type": "done",
                "artifacts": output.artifacts,
                "cost_cents": output.cost_cents,
                "success": output.success,
            })

    except WebSocketDisconnect:
        logger.info(f"WS client disconnected: {request_id}")
    except Exception as e:
        logger.exception(f"WS error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
        await websocket.close()


# ---- SSE (Server-Sent Events, 适用于浏览器 EventSource) ----

from fastapi.responses import StreamingResponse


@router.get("/sse/invoke")
async def sse_invoke(
    text: str = Query(...),
    agent_name: str = Query(default=""),
    token: str = Query(...),
):
    """SSE 流式调用, 浏览器 EventSource 兼容."""
    from api.auth import decode_supabase_jwt
    payload = decode_supabase_jwt(token)
    user_id = payload.get("sub", "anonymous")
    persona = payload.get("user_metadata", {}).get("role", "jobseeker")

    rt = get_router()
    name = agent_name or rt.route(text, persona=persona)
    agent = registry.get_or_raise(name)

    async def event_gen():
        yield f"event: start\ndata: {json.dumps({'agent': name})}\n\n"
        agent_input = AgentInput(user_id=user_id, persona=persona, text=text)
        output = await agent.run(agent_input)
        for i in range(0, len(output.text), 20):
            yield f"event: chunk\ndata: {json.dumps({'text': output.text[i:i+20]})}\n\n"
            await asyncio.sleep(0.02)
        yield f"event: done\ndata: {json.dumps({'artifacts': output.artifacts, 'success': output.success})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")