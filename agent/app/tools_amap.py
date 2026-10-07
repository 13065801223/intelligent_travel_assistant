# -*- coding: utf-8 -*-
"""把模型能用的高德工具映射到 MCP 调用。

参数统一 str() 转换：amap-mcp-server 的 schema 里 `citylimit` 是字符串，否则会校验失败。
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from .mcp_client import AmapMCPClient

# 工具名 -> 异步执行函数
ToolFn = Callable[[dict[str, Any]], Awaitable[str]]

# 暴露给模型的工具白名单（同时用于提示词里的工具表）
EXPOSED_TOOLS: frozenset[str] = frozenset({"maps_text_search", "maps_weather"})


class AmapTools:
    """薄封装：只做参数整形，不做结果解析。

    结果保持原始文本回灌给模型，让它自己摘取字段，不必为每个工具写解析器。
    """

    def __init__(self, mcp: AmapMCPClient) -> None:
        self._mcp = mcp

    async def maps_text_search(self, args: dict[str, Any]) -> str:
        payload = {
            "keywords": str(args.get("keywords", "")).strip(),
            "city": str(args.get("city", "")).strip(),
            "citylimit": str(args.get("citylimit", "false")).strip().lower() or "false",
        }
        return await self._mcp.call("maps_text_search", payload)

    async def maps_weather(self, args: dict[str, Any]) -> str:
        payload = {"city": str(args.get("city", "")).strip()}
        return await self._mcp.call("maps_weather", payload)

    def registry(self) -> dict[str, ToolFn]:
        """给 Agent 循环用的工具表（只暴露白名单内的两个）。"""

        return {
            "maps_text_search": self.maps_text_search,
            "maps_weather": self.maps_weather,
        }
