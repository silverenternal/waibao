"""分布式追踪 — OpenTelemetry 风格 span 记录.

MVP 阶段: 内存 span + 日志
生产阶段: 接入 LangSmith / Arize Phoenix / OTLP collector
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("recruittech.agents.tracing")


@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    parent_span_id: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    attributes: dict = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)

    def set(self, key: str, value):
        self.attributes[key] = value

    def event(self, name: str, **attrs):
        self.events.append({"name": name, "ts": time.time(), **attrs})

    def end(self):
        self.ended_at = time.time()

    @property
    def duration_ms(self) -> int:
        end = self.ended_at or time.time()
        return int((end - self.started_at) * 1000)


class Tracer:
    def __init__(self):
        self._stack: list[Span] = []

    def start_span(self, name: str, trace_id: Optional[str] = None) -> Span:
        parent = self._stack[-1].span_id if self._stack else None
        tid = trace_id or (self._stack[0].trace_id if self._stack else str(uuid.uuid4())[:12])
        span = Span(name=name, trace_id=tid, parent_span_id=parent)
        self._stack.append(span)
        logger.debug(f"[trace {tid}] span start: {name} ({span.span_id}) parent={parent}")
        return span

    def end_span(self):
        if not self._stack:
            return
        span = self._stack.pop()
        span.end()
        logger.info(
            f"[trace {span.trace_id}] span end: {span.name} "
            f"({span.duration_ms}ms, parent={span.parent_span_id})"
        )

    @property
    def current(self) -> Optional[Span]:
        return self._stack[-1] if self._stack else None


# 全局 tracer 实例
tracer = Tracer()