# -*- coding: utf-8 -*-
"""Agent 循环：文本工具协议 `[TOOL_CALL:工具名:参数=值,...]`。

模型输出工具调用 → 我们解析执行 → 结果回灌，最多 N 轮，然后要一次最终回答。
用文本协议而非原生 function calling：与旧提示词最接近，且日志里能直接看到模型发什么。

两处改进：系统提示词注入真实注册的工具表；未知工具不中断整轮，而是回灌可用清单让模型自我纠正。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Awaitable, Callable

from .config import Settings
from .llm import LLMClient

logger = logging.getLogger(__name__)

# [TOOL_CALL:maps_text_search:keywords=西湖,city=杭州]
TOOL_CALL_RE = re.compile(r"\[TOOL_CALL:([A-Za-z0-9_]+):(.*?)\]", re.S)

ToolFn = Callable[[dict[str, str]], Awaitable[str]]
ToolBlockProvider = Callable[[], str]


def parse_tool_calls(text: str) -> list[tuple[str, dict[str, str]]]:
    """解析文本里的工具调用。参数按 `k=v` 逗号分隔解析（与旧协议一致）。"""

    calls: list[tuple[str, dict[str, str]]] = []
    for name, raw in TOOL_CALL_RE.findall(text or ""):
        args: dict[str, str] = {}
        for part in raw.split(","):
            if "=" in part:
                key, value = part.split("=", 1)
                args[key.strip()] = value.strip()
        calls.append((name, args))
    return calls


class ToolAgent:
    """带工具的 Agent（景点 / 天气 / 酒店 三个都用它）。"""

    def __init__(
        self,
        name: str,
        system_prompt: str,
        llm: LLMClient,
        tools: dict[str, ToolFn],
        settings: Settings,
        tool_block_provider: ToolBlockProvider,
    ) -> None:
        self.name = name
        self._system_prompt = system_prompt
        self._llm = llm
        self._tools = tools
        self._max_iterations = max(1, settings.agent_max_tool_iterations)
        # 用 provider 而非构造时快照：工具表可能在运行期变化（MCP 重连），每次 run 取最新
        self._tool_block_provider = tool_block_provider

    def _system_message(self) -> str:
        tool_block = self._tool_block_provider()
        return (
            f"{self._system_prompt}\n\n"
            f"**当前真实可用的工具（只能使用这些名字，不要凭记忆编造）:**\n{tool_block}"
        )

    async def run(self, user_input: str) -> str:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_message()},
            {"role": "user", "content": user_input},
        ]

        for iteration in range(self._max_iterations):
            text = await self._llm.chat(messages)
            calls = parse_tool_calls(text)
            if not calls:
                logger.info("[%s] 第 %d 轮结束（无工具调用）", self.name, iteration + 1)
                return text

            logger.info(
                "[%s] 第 %d 轮请求工具：%s",
                self.name,
                iteration + 1,
                ", ".join(name for name, _ in calls),
            )
            messages.append({"role": "assistant", "content": text})

            results: list[str] = []
            for tool_name, args in calls:
                tool = self._tools.get(tool_name)
                if tool is None:
                    # 不抛异常：回灌可用清单让模型自己改对
                    results.append(
                        f"工具 {tool_name} 不存在。可用工具只有："
                        f"{', '.join(sorted(self._tools))}"
                    )
                    continue
                try:
                    output = await tool(args)
                except Exception as exc:  # MCPUnavailable 等
                    logger.warning("[%s] 工具 %s 失败：%s", self.name, tool_name, exc)
                    results.append(f"工具 {tool_name} 执行失败：{exc}")
                    continue
                results.append(f"工具 {tool_name} 结果：\n{output}")

            messages.append(
                {
                    "role": "user",
                    "content": (
                        "工具执行结果：\n"
                        + "\n\n".join(results)
                        + "\n\n请基于以上结果给出最终回答。"
                    ),
                }
            )

        # 轮次用尽：再要一次不带工具的最终回答，避免把中间过程当结果
        messages.append({"role": "user", "content": "请直接给出最终回答，不要再调用工具。"})
        return await self._llm.chat(messages)


class PlainAgent:
    """无工具的 Agent（行程规划用：它是"整合者"，不需要外部数据）。"""

    def __init__(self, name: str, system_prompt: str, llm: LLMClient) -> None:
        self.name = name
        self._system_prompt = system_prompt
        self._llm = llm

    async def run(self, user_input: str) -> str:
        return await self._llm.chat(
            [
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": user_input},
            ]
        )
