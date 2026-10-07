# -*- coding: utf-8 -*-
"""统一错误体系：每个异常自带 `code` 与 `http_status`，由 main.py 翻译成
`{"error": {"code","message","trace_id"}}`。
"""

from __future__ import annotations


class AgentError(Exception):
    """Agent 服务所有可预期错误的基类。"""

    code: str = "AGENT_ERROR"
    http_status: int = 500

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.cause = cause


class LLMTimeout(AgentError):
    """单次 LLM 调用超时。属于硬失败：模型不可用，不能靠降级糊过去。"""

    code = "LLM_TIMEOUT"
    http_status = 504


class LLMError(AgentError):
    """模型返回错误/限流/协议异常。硬失败。"""

    code = "LLM_ERROR"
    http_status = 502


class MCPUnavailable(AgentError):
    """高德 MCP 不可用。

    软失败：编排器记降级继续，并在 health 里暴露为 degraded。
    """

    code = "MCP_UNAVAILABLE"
    http_status = 502


class PlanParseFailed(AgentError):
    """行程输出无法解析成冻结契约。硬失败，不做"编假行程"兜底。"""

    code = "PLAN_PARSE_FAILED"
    http_status = 502


class DeadlineExceeded(AgentError):
    """超出整条链路的时间预算。"""

    code = "DEADLINE_EXCEEDED"
    http_status = 504
