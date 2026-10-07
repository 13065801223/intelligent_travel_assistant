# -*- coding: utf-8 -*-
"""LLM 客户端：把 messages 发到 OpenAI 兼容端点（ModelScope），取回纯文本。

对 429/5xx 做**有界**重试（见 _create_with_retry），其余错误直接抛业务异常。
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Sequence

import httpx
from openai import APIConnectionError, APIError, APITimeoutError, AsyncOpenAI

from .config import Settings
from .errors import LLMError, LLMTimeout

logger = logging.getLogger(__name__)

# 只对瞬时错误重试：限流 / 上游 5xx
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

# 这两类不走退避：超时已吃满 LLM_TIMEOUT，连不上属于网络/配置问题
_TRANSIENT_PASS_THROUGH = (APITimeoutError, APIConnectionError)


def _status_of(exc: Exception) -> int | None:
    """从异常里取 HTTP 状态码（openai SDK 会把 response 挂在异常上）。"""

    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


class _RetryBudget:
    """重试等待的总时长预算，防止退避把 agent 的 570s 预算吃光。"""

    def __init__(self, seconds: float) -> None:
        self._remaining = max(0.0, seconds)

    def allow(self, delay: float) -> bool:
        if delay > self._remaining:
            return False
        self._remaining -= delay
        return True

    @property
    def remaining(self) -> float:
        return self._remaining


def build_payload(
    settings: Settings,
    messages: Sequence[dict[str, Any]],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """组装一次调用的 body（纯函数，便于测试）。

    `reasoning_effort` 仅在配置非空时带上；留空即不传，交给端点默认。
    """

    payload: dict[str, Any] = {
        "model": settings.llm_model_id,
        "messages": list(messages),
        "temperature": settings.llm_temperature if temperature is None else temperature,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens
    if settings.llm_reasoning_effort.strip():
        payload["reasoning_effort"] = settings.llm_reasoning_effort.strip()
    return payload


class LLMClient:
    """对整个服务只保留一个实例（见 main.py 的 lifespan）。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout,
            # 传输层不重试：退避策略由 _create_with_retry 统一管，避免两套重试叠加
            max_retries=0,
        )
        # 便于测试注入"不真的睡觉"
        self._sleep = asyncio.sleep

    async def _create_with_retry(self, payload: dict[str, Any]):
        """调用补全，对 429/5xx 做有界退避重试。

        只重试 RETRYABLE_STATUS；等待总时长受 LLM_RETRY_BUDGET_SECONDS 封顶；
        退避带抖动以错开并行 Agent；用尽即抛 LLMError。
        """

        attempt = 0
        budget = _RetryBudget(self._settings.llm_retry_budget_seconds)
        while True:
            try:
                return await self._client.chat.completions.create(**payload)
            except _TRANSIENT_PASS_THROUGH:
                # 超时/连不上：交给 chat() 翻译，不在这里退避
                raise
            except (APIError, httpx.HTTPStatusError) as exc:
                status = _status_of(exc)
                if attempt >= self._settings.llm_retries or status not in RETRYABLE_STATUS:
                    raise
                delay = min(2.0 * (2**attempt), 8.0) * (0.5 + random.random())
                if not budget.allow(delay):
                    logger.warning(
                        "LLM %s 重试等待会超出预算（剩余 %.1fs），直接失败",
                        status,
                        budget.remaining,
                    )
                    raise
                attempt += 1
                logger.warning(
                    "LLM 返回 %s，第 %d 次重试（等待 %.1fs，重试预算剩 %.1fs）",
                    status,
                    attempt,
                    delay,
                    budget.remaining,
                )
                await self._sleep(delay)

    async def chat(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """一次对话补全。异常按语义翻译成 LLMTimeout / LLMError。"""

        payload = build_payload(
            self._settings, messages, temperature=temperature, max_tokens=max_tokens
        )
        try:
            response = await self._create_with_retry(payload)
        except APITimeoutError as exc:
            raise LLMTimeout(f"LLM 调用超时（{self._settings.llm_timeout}s）") from exc
        except APIConnectionError as exc:
            raise LLMError(f"无法连接 LLM：{exc}") from exc
        except (APIError, httpx.HTTPStatusError) as exc:
            # httpx 兜底：SDK 之外的传输层错误也必须是 LLMError（错误体要统一带 code）
            raise LLMError(f"LLM 返回错误：{exc}") from exc

        if not response.choices:
            raise LLMError("LLM 返回了空 choices")

        text = (response.choices[0].message.content or "").strip()
        # 隐藏推理量一并记录：它是延迟的最大单笔开销
        reasoning = getattr(response.choices[0].message, "reasoning_content", None) or ""
        usage = getattr(response, "usage", None)
        logger.debug(
            "LLM 输出 %d 字符（隐藏推理 %d 字符，completion_tokens=%s）",
            len(text),
            len(reasoning),
            getattr(usage, "completion_tokens", "?"),
        )
        return text

    async def aclose(self) -> None:
        await self._client.close()
