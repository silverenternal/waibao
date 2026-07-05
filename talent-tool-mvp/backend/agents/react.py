"""ReAct-style Agent — Thought → Action → Observation 循环.

设计哲学:
- ❌ 单次 LLM 调用 + 模板填空
- ✅ Agent 自己思考 → 决定调用什么工具 → 观察结果 → 继续推理
- ✅ 推理过程对用户可见
- ✅ 支持自我反思和迭代
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient

logger = logging.getLogger("recruittech.agents.react")


@dataclass
class ReasoningStep:
    """单步推理,可见给用户."""
    step_num: int
    thought: str                    # agent 在想什么
    action: Optional[str] = None    # 它决定做什么
    action_input: Optional[dict] = None
    observation: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class ToolSpec:
    """Tool 描述(给 LLM 看)."""
    name: str
    description: str               # LLM 看的自然语言描述
    parameters: dict               # JSON Schema
    handler: Callable[..., Awaitable[Any]]

    def to_llm_spec(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


REACT_SYSTEM = """你是一个有推理能力的智能体。

工作方式:
1. Thought: 先思考下一步该做什么
2. Action: 决定调用哪个工具 (action=name, action_input={...})
3. Observation: 收到工具返回后,继续推理
4. 直到能给出 Final Answer

输出格式 (每次只能输出一种):

--- 如果继续推理 ---
Thought: <你的思考>
Action: <tool_name>
Action Input: <JSON 参数>

--- 如果已经能回答 ---
Thought: 我已经收集了足够信息
Final Answer: <给用户的最终回答>
"""


class ReActAgent(BaseAgent):
    """支持 Thought → Action → Observation 循环的 Agent 基类."""

    max_iterations: int = 5
    reasoning_echo: bool = True     # 是否把推理过程返回给前端

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tools: dict[str, ToolSpec] = {}

    def register_tool(self, name: str, description: str, parameters: dict,
                      handler: Callable[..., Awaitable[Any]]):
        """注册工具(比 BaseAgent 更详细)."""
        spec = ToolSpec(name=name, description=description,
                       parameters=parameters, handler=handler)
        self.tools[name] = spec
        # 同时也注册到 BaseAgent 的 _tools (向后兼容)
        super().register_tool(name, handler)

    async def _handle(self, agent_input: AgentInput) -> AgentOutput:
        """ReAct 主循环."""
        reasoning_steps: list[ReasoningStep] = []
        step_num = 0
        final_answer: Optional[str] = None

        for iteration in range(self.max_iterations):
            step_num += 1

            # 1. Thought + Action: 让 LLM 决定下一步
            prompt = self._build_react_prompt(agent_input, reasoning_steps)
            tools_spec = [t.to_llm_spec() for t in self.tools.values()]

            try:
                response = await self.llm.call(
                    messages=[
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": prompt},
                    ],
                    response_format=None,   # 不要 JSON mode,让 LLM 自然推理
                    max_cost_cents=20,
                )
            except Exception as e:
                logger.exception(f"ReAct iteration {iteration} failed: {e}")
                break

            # 2. 解析 LLM 输出: Thought / Action / Final Answer
            step = self._parse_react_response(response, step_num)
            reasoning_steps.append(step)

            # 3. 如果 LLM 已经给出 Final Answer,结束
            if step.action == "FinalAnswer":
                final_answer = step.thought   # thought 里包含 final answer
                break

            # 4. 否则执行 Action
            if step.action and step.action in self.tools:
                try:
                    result = await self.tools[step.action].handler(
                        **(step.action_input or {})
                    )
                    step.observation = json.dumps(result, ensure_ascii=False)[:2000]
                except Exception as e:
                    step.observation = f"Error: {e}"
            elif step.action:
                step.observation = f"Unknown tool: {step.action}"
            else:
                # 既不是 FinalAnswer 也没指定 action,终止
                break

            # 5. 自我反思: 每 2 步让 LLM 反思一下方向
            if iteration == self.max_iterations - 2:
                reflection_step = await self._reflect(reasoning_steps)
                reasoning_steps.append(reflection_step)
                if reflection_step.action == "FinalAnswer":
                    final_answer = reflection_step.thought
                    break

        # 6. 组装输出
        if final_answer is None:
            final_answer = self._synthesize_fallback(reasoning_steps)

        return AgentOutput(
            agent_name=self.name,
            text=final_answer,
            artifacts={
                "reasoning_steps": [
                    {
                        "step": s.step_num,
                        "thought": s.thought,
                        "action": s.action,
                        "observation": s.observation,
                    }
                    for s in reasoning_steps
                ],
                "iterations": len(reasoning_steps),
            },
            memory_writes=[],
            signals=[],
        )

    def _build_react_prompt(self, agent_input: AgentInput,
                            history: list[ReasoningStep]) -> str:
        """构建当前 ReAct 提示."""
        parts = [f"用户输入: {agent_input.text}"]
        if agent_input.context:
            parts.append(f"上下文: {json.dumps(agent_input.context, ensure_ascii=False)[:1000]}")

        if history:
            parts.append("\n之前的推理:")
            for s in history:
                parts.append(f"\nStep {s.step_num}:")
                parts.append(f"  Thought: {s.thought}")
                if s.action:
                    parts.append(f"  Action: {s.action}")
                    if s.action_input:
                        parts.append(f"  Action Input: {json.dumps(s.action_input, ensure_ascii=False)}")
                if s.observation:
                    parts.append(f"  Observation: {s.observation[:500]}")

        parts.append("\n下一步:")
        return "\n".join(parts)

    def _parse_react_response(self, response: str, step_num: int) -> ReasoningStep:
        """解析 LLM 的 ReAct 输出."""
        step = ReasoningStep(step_num=step_num, thought=response)

        # 检测 Final Answer
        if "Final Answer:" in response:
            idx = response.find("Final Answer:")
            step.action = "FinalAnswer"
            step.thought = response[idx + len("Final Answer:"):].strip()
            return step

        # 检测 Action
        thought = ""
        action = None
        action_input = None

        if "Thought:" in response:
            thought = response.split("Thought:")[1]
            if "Action:" in thought:
                thought = thought.split("Action:")[0].strip()

        if "Action:" in response:
            after_action = response.split("Action:")[1]
            if "Action Input:" in after_action:
                action_part, input_part = after_action.split("Action Input:", 1)
                action = action_part.strip().split()[0] if action_part.strip() else None
                # 尝试解析 JSON
                try:
                    action_input = json.loads(input_part.strip())
                except json.JSONDecodeError:
                    action_input = {"raw": input_part.strip()}
            else:
                action = after_action.strip().split()[0]

        step.thought = thought.strip() if thought else response[:500]
        step.action = action
        step.action_input = action_input
        return step

    async def _reflect(self, history: list[ReasoningStep]) -> ReasoningStep:
        """自我反思: 我做的对吗? 是否需要调整方向?"""
        recent = history[-3:]
        reflection_prompt = f"""反思一下当前的推理过程是否合理:

{chr(10).join(f'Step {s.step_num}: Thought={s.thought[:100]}, Action={s.action}, Obs={s.observation[:100] if s.observation else None}' for s in recent)}

现在你能给出最终回答吗? 如果可以,写"Final Answer: ..."
如果还需要更多推理,写"Thought: ..." 和下一步 Action."""

        try:
            response = await self.llm.call(
                [{"role": "user", "content": reflection_prompt}],
                max_cost_cents=10,
            )
            return self._parse_react_response(response, len(history) + 1)
        except Exception:
            return ReasoningStep(
                step_num=len(history) + 1,
                thought="Reflection failed, falling back",
                action="FinalAnswer",
            )

    def _synthesize_fallback(self, steps: list[ReasoningStep]) -> str:
        """ReAct 超时/失败时的兜底回答."""
        if not steps:
            return "抱歉,我没有想出好的方案。"
        # 把所有 observation 拼起来作为兜底
        obs = [s.observation for s in steps if s.observation]
        return "\n".join(obs) if obs else "推理完成,但没收集到有效信息。"

    def _get_system_prompt(self) -> str:
        """子类可覆盖."""
        return REACT_SYSTEM