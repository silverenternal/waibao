"""Realtime API — WebSocket 端点 + SSE.

支持:
    1. 求职者/用人方召唤 agent (/ws/invoke, /sse/invoke) — 沿用 v2.0
    2. 多人协同房间广播 (/ws/rooms/{room_id}) — T608 新增:
       - 客户端发送 {type:"subscribe", token}, 服务端校验成员身份
       - 客户端发送 {type:"publish", delivery_id, payload}
       - 服务端广播 {type:"message", delivery_id, sender, payload}
       - 服务端回 {type:"ack", delivery_id, status}
       - 使用本地 ConnectionManager (单实例); 多实例时切换 Redis pub/sub
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
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


# ============================================================================
# T608 — 多人协同房间 WebSocket
# ============================================================================
#
# 协议 (双向 JSON):
#
#   客户端 -> 服务端:
#     {"type": "hello", "token": "<jwt>", "room_id": "<uuid>"}
#     {"type": "publish", "delivery_id": "<uuid>", "event": "message",
#      "payload": { ... }}
#     {"type": "typing", "payload": {"is_typing": true}}
#     {"type": "ping"}
#
#   服务端 -> 客户端:
#     {"type": "ready", "user_id": "...", "room_id": "..."}
#     {"type": "ack", "delivery_id": "...", "status": "ok" | "error",
#      "error": "..." }
#     {"type": "broadcast", "event": "message"|"reaction"|"presence"|"read"|
#                                "typing"|"member_join"|"member_leave",
#      "sender": "<user_id>", "payload": { ... }, "ts": "..."}
#     {"type": "pong", "ts": "..."}
#     {"type": "error", "message": "..."}
#
# 多实例时, 通过 Redis pub/sub 桥接不同 Pod 上的房间 (REDIS_URL 环境变量启用).
# 单实例 (默认) 使用本地 ConnectionManager.
# ----------------------------------------------------------------------------

class _RoomConnectionManager:
    """本地 room_id → 一组 WebSocket 的多路复用器."""

    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = {}
        self._user_to_ws: dict[str, tuple[str, WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, room_id: str, user_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._rooms.setdefault(room_id, set()).add(ws)
            self._user_to_ws[user_id] = (room_id, ws)

    async def disconnect(self, room_id: str, user_id: str, ws: WebSocket) -> None:
        async with self._lock:
            conns = self._rooms.get(room_id)
            if conns is not None:
                conns.discard(ws)
                if not conns:
                    self._rooms.pop(room_id, None)
            stored = self._user_to_ws.get(user_id)
            if stored and stored[1] is ws:
                self._user_to_ws.pop(user_id, None)

    async def broadcast(self, room_id: str, message: dict) -> int:
        """广播到房间所有连接, 返回成功发送的连接数."""
        async with self._lock:
            conns = list(self._rooms.get(room_id, ()))
        sent = 0
        for ws in conns:
            try:
                await ws.send_json(message)
                sent += 1
            except Exception:  # noqa: BLE001
                # 静默失败: 对端已断, 后台 task 负责清理
                pass
        return sent


_room_manager = _RoomConnectionManager()


def _redis_channel(room_id: str) -> str:
    return f"rooms:{room_id}"


async def _redis_publish(room_id: str, message: dict) -> bool:
    """若环境变量 REDIS_URL 设置, 推送到 redis pub/sub; 否则 False."""
    url = os.getenv("REDIS_URL")
    if not url:
        return False
    try:
        import redis.asyncio as redis  # type: ignore

        client = redis.from_url(url)
        await client.publish(_redis_channel(room_id), json.dumps(message))
        await client.close()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("redis publish failed: %s", exc)
        return False


@router.websocket("/ws/rooms/{room_id}")
async def ws_room(
    websocket: WebSocket,
    room_id: str,
    token: Optional[str] = Query(default=None),
):
    """房间 WebSocket 端点 — 多方实时对话.

    使用 delivery_id + ack 模式: 客户端 publish 时携带 delivery_id, 服务端
    处理完成回 ack {delivery_id, status}; 广播事件带 sender/timestamp.
    """
    await websocket.accept()

    # 默认 token 也可走 Sec-WebSocket-Protocol / 首条消息携带 (略)
    auth_token = token
    if not auth_token:
        # 退路: 第一条消息必须是 {type:"hello", token:..., room_id:...}
        try:
            first = await asyncio.wait_for(websocket.receive_text(), timeout=5)
            msg = json.loads(first)
        except Exception:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        if msg.get("type") != "hello" or not msg.get("token"):
            await websocket.send_json({"type": "error", "message": "missing token"})
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        auth_token = msg.get("token")

    # 鉴权
    try:
        from api.auth import decode_supabase_jwt
        from api.deps import get_supabase_admin
        payload = decode_supabase_jwt(auth_token)
    except HTTPException as e:
        await websocket.send_json({"type": "error", "message": e.detail})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_id = payload.get("sub", "anonymous")

    # 校验用户是 room 成员
    try:
        from services.collaboration_room import _check_member
        _check_member(get_supabase_admin(), room_id, user_id)
    except Exception as e:  # noqa: BLE001
        await websocket.send_json({"type": "error", "message": f"not member: {e}"})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 加入广播组
    await _room_manager.connect(room_id, user_id, websocket)
    broadcast_join = {
        "type": "broadcast",
        "event": "member_join",
        "sender": user_id,
        "payload": {"user_id": user_id, "room_id": room_id},
        "ts": asyncio.get_event_loop().time(),
    }
    await _room_manager.broadcast(room_id, broadcast_join)
    await _redis_publish(room_id, broadcast_join)

    await websocket.send_json({
        "type": "ready",
        "user_id": user_id,
        "room_id": room_id,
    })

    async def relay(event: str, payload: dict, sender: str = user_id) -> None:
        msg = {
            "type": "broadcast",
            "event": event,
            "sender": sender,
            "payload": payload,
            "ts": asyncio.get_event_loop().time(),
        }
        await _room_manager.broadcast(room_id, msg)
        await _redis_publish(room_id, msg)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "invalid json"})
                continue

            mtype = msg.get("type")

            if mtype == "ping":
                await websocket.send_json({"type": "pong", "ts": msg.get("ts")})
                continue

            if mtype == "publish":
                delivery_id = msg.get("delivery_id") or str(uuid.uuid4())
                event = msg.get("event") or "message"
                payload = msg.get("payload") or {}

                # 写入数据库: 仅 message 事件直写, 其它交给 REST
                if event == "message":
                    try:
                        from services.collaboration_room import post_message
                        from api.deps import get_supabase_admin
                        sb = get_supabase_admin()
                        msg_row = post_message(
                            sb,
                            room_id,
                            sender_id=user_id,
                            content=payload.get("content", ""),
                            message_type=payload.get("message_type", "text"),
                            parent_id=payload.get("parent_id"),
                            mentions=payload.get("mentions"),
                            mention_offsets=payload.get("mention_offsets"),
                            attachments=payload.get("attachments"),
                        )
                        await websocket.send_json({
                            "type": "ack",
                            "delivery_id": delivery_id,
                            "status": "ok",
                            "message_id": msg_row.id,
                            "created_at": msg_row.created_at,
                        })
                        await relay(
                            "message",
                            {
                                **payload,
                                "message_id": msg_row.id,
                                "created_at": msg_row.created_at,
                                "sender_id": user_id,
                            },
                        )
                    except Exception as e:  # noqa: BLE001
                        await websocket.send_json({
                            "type": "ack",
                            "delivery_id": delivery_id,
                            "status": "error",
                            "error": str(e),
                        })
                    continue

                # 其它事件 (typing / read / reaction / presence) 仅广播
                await relay(event, payload)
                await websocket.send_json({
                    "type": "ack",
                    "delivery_id": delivery_id,
                    "status": "ok",
                })
                continue

            if mtype in ("typing", "presence", "read"):
                # 轻量事件: 不写盘, 直接广播, 不回 ack (降低噪声)
                await relay(mtype, msg.get("payload") or {})
                continue

            # 未知类型: 回 error 但不退出
            await websocket.send_json({
                "type": "error",
                "message": f"unknown message type: {mtype}",
            })

    except WebSocketDisconnect:
        logger.info("WS room %s: user %s disconnected", room_id, user_id)
    except Exception as e:  # noqa: BLE001
        logger.exception("WS room error: %s", e)
    finally:
        await _room_manager.disconnect(room_id, user_id, websocket)
        leave_msg = {
            "type": "broadcast",
            "event": "member_leave",
            "sender": user_id,
            "payload": {"user_id": user_id, "room_id": room_id},
            "ts": asyncio.get_event_loop().time(),
        }
        await _room_manager.broadcast(room_id, leave_msg)
        await _redis_publish(room_id, leave_msg)