# -*- coding: utf-8 -*-
"""Agent 服务配置：把 agent/.env 读成强类型对象。

env_file 用绝对路径，保证从任何工作目录启动 uvicorn 都读到同一个 .env。
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# app/config.py -> app -> agent -> intelligent_travel_assistant
REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = REPO_ROOT / "agent"


class Settings(BaseSettings):
    """全部字段都能用同名大写环境变量覆盖（pydantic-settings 大小写不敏感）。"""

    model_config = SettingsConfigDict(
        env_file=str(AGENT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- LLM ----
    llm_api_key: str = ""
    llm_base_url: str = "https://api-inference.modelscope.cn/v1"
    llm_model_id: str = "Qwen/Qwen3.8-Flash-Next"
    # 单次 LLM 调用超时（秒）。必须 < AGENT_DEADLINE_SECONDS < BFF 的 590s。
    llm_timeout: int = 300
    llm_temperature: float = 0.7

    # 隐藏推理档位（留空 = 不传，交给端点默认）。不压的话单次调用可能撞上 llm_timeout。
    llm_reasoning_effort: str = "low"

    # 429/5xx 的有界重试（三个检索 Agent 并行发请求，容易一起撞上端点限流）。
    # 必须有界：整条链路只有 570s 软预算，无界重试会把预算吃光。
    llm_retries: int = 3
    # 重试等待的总时长上限（秒），并行 Agent 用抖动错开。
    llm_retry_budget_seconds: float = 20.0

    # ---- 高德：只交给 MCP 子进程，本服务自己不直接调高德 REST ----
    amap_api_key: str = ""

    # ---- 服务 ----
    host: str = "127.0.0.1"
    port: int = 8100
    log_level: str = "INFO"

    # ---- 运行模式 ----
    # stub：不碰 LLM/MCP，直接返回契约黄金样本，让 BFF 与前端开发期零成本联调
    # real：真实链路
    agent_mode: str = "stub"

    # 整条链路的软预算（秒）。超过就抛 DEADLINE_EXCEEDED，而不是让 BFF 先超时。
    agent_deadline_seconds: int = 570
    agent_max_tool_iterations: int = 3

    # 契约黄金样本（stub 模式返回它的 data 部分；也是两端的唯一权威样本）
    contract_sample: str = str(REPO_ROOT / "contracts" / "trip-plan.sample.json")

    # MCP 服务器启动方式
    mcp_command: str = "uvx"
    mcp_args: str = "amap-mcp-server"

    # 给 uvx 子进程指定 PyPI 索引（留空 = uv 默认的 pypi.org，本机实测其索引页要 180s）。
    #   MCP_UV_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
    mcp_uv_index: str = ""

    # uvx 的缓存/工具目录（留空 = 用 uv 默认的 %LOCALAPPDATA%\uv\...）。
    # 必须钉在仓库内：uv 默认缓存在工作区之外，只读沙箱下 uvx 打不开就 exit 2。
    mcp_uv_cache_dir: str = ""
    mcp_uv_tool_dir: str = ""

    # ---- MCP 传输方式 ----
    # http（默认）：服务器作为独立进程起在 mcp_http_host:port，输出落 agent/logs/mcp-server.log，不碰管道。
    # stdio：交给 mcp 库用管道起子进程（本机会 [WinError 5]，保留兼容）。
    mcp_transport: str = "http"
    mcp_http_host: str = "127.0.0.1"
    mcp_http_port: int = 8199
    # 等服务器监听端口的秒数；首次运行要 uvx 下载，给足余量。
    mcp_start_timeout: int = 120

    @property
    def mcp_arg_list(self) -> list[str]:
        return [part for part in self.mcp_args.split() if part]

    @property
    def is_stub(self) -> bool:
        return self.agent_mode.strip().lower() == "stub"


settings = Settings()
