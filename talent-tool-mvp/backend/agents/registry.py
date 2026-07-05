"""智能体注册中心 — 全局单例管理所有 Agent.

提供:
- register / get / list 接口
- 按 persona 过滤可用 agent
- 健康检查
"""
from __future__ import annotations

import logging
from typing import Optional

from agents.runtime import BaseAgent

logger = logging.getLogger("recruittech.agents.registry")


class AgentRegistry:
    """全局 Agent 注册中心."""

    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}
        self._aliases: dict[str, str] = {}

    def register(self, agent: BaseAgent, aliases: Optional[list[str]] = None):
        if agent.name in self._agents:
            logger.warning(f"Overriding existing agent '{agent.name}'")
        self._agents[agent.name] = agent
        if aliases:
            for a in aliases:
                self._aliases[a] = agent.name
        logger.info(f"Registered agent: {agent.name}")

    def get(self, name_or_alias: str) -> Optional[BaseAgent]:
        if name_or_alias in self._agents:
            return self._agents[name_or_alias]
        if name_or_alias in self._aliases:
            return self._agents[self._aliases[name_or_alias]]
        return None

    def get_or_raise(self, name: str) -> BaseAgent:
        agent = self.get(name)
        if agent is None:
            raise KeyError(f"Agent '{name}' not registered")
        return agent

    def list_for_persona(self, persona: str) -> list[str]:
        return [
            n for n, a in self._agents.items()
            if not a.required_personas or persona in a.required_personas
        ]

    def all_names(self) -> list[str]:
        return list(self._agents.keys())

    async def health_check(self) -> dict[str, str]:
        return {n: "ok" for n in self._agents}


# 全局单例
registry = AgentRegistry()