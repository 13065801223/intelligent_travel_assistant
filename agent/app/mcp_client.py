# -*- coding: utf-8 -*-
"""MCP 客户端：HTTP 传输（默认）+ stdio 可选。

默认 HTTP：把服务器当独立进程起在 127.0.0.1，stdout/stderr 落文件、协议走 socket，
不碰子进程管道。stdio 分支在本机会 `[WinError 5] 拒绝访问`（mcp 库建进程那步被拒），
可用 MCP_TRANSPORT=stdio 切回。

uv 缓存必须钉在仓库内（见 DEFAULT_UV_CACHE_DIR）：uv 默认写 %LOCALAPPDATA%，
只读沙箱下 uvx 打不开自己的缓存就 exit 2。两种传输共用同一个 uvx。
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from .config import REPO_ROOT, Settings
from .errors import MCPUnavailable

logger = logging.getLogger(__name__)

# 行程链路真正依赖的两个工具，缺一个都不该启动成功
REQUIRED_TOOLS: frozenset[str] = frozenset({"maps_text_search", "maps_weather"})

TRANSPORT_HTTP = "http"
TRANSPORT_STDIO = "stdio"

# 子进程输出的落盘位置（preflight 会打印它）
LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
SERVER_LOG = LOG_DIR / "mcp-server.log"

# uvx 的缓存/工具目录默认落点，必须在仓库内。
# uv 默认写 %LOCALAPPDATA%\uv\{cache,tools}（工作区外），只读沙箱下 uvx 打不开自己的
# 缓存就 exit 2。与传输方式无关：stdio 和 HTTP 都是同一个 uvx。
DEFAULT_UV_CACHE_DIR = REPO_ROOT / ".uvcache"
DEFAULT_UV_TOOL_DIR = REPO_ROOT / ".uvtools"


def _uv_dir(configured: str, default: Path) -> str:
    """uv 缓存/工具目录：配置优先，否则用仓库内默认落点（永远是绝对路径）。"""

    chosen = Path(configured.strip()) if configured.strip() else default
    return str(chosen.resolve())


def build_subprocess_env(settings: Settings) -> dict[str, str]:
    """构造 MCP 子进程环境变量（运行时与 preflight 共用同一份实现）。

    继承 os.environ（PATH 里找 uvx）；注入高德 key；可选换 PyPI 镜像；
    把 uv 缓存/工具目录钉在仓库内；HTTP 传输时用 FASTMCP_* 指定监听地址与端口。
    """

    env = {**os.environ, "AMAP_MAPS_API_KEY": settings.amap_api_key}
    if settings.mcp_uv_index.strip():
        env["UV_DEFAULT_INDEX"] = settings.mcp_uv_index.strip()
    env["UV_CACHE_DIR"] = _uv_dir(settings.mcp_uv_cache_dir, DEFAULT_UV_CACHE_DIR)
    env["UV_TOOL_DIR"] = _uv_dir(settings.mcp_uv_tool_dir, DEFAULT_UV_TOOL_DIR)
    if (settings.mcp_transport or "").strip().lower() == TRANSPORT_HTTP:
        env["FASTMCP_HOST"] = settings.mcp_http_host
        env["FASTMCP_PORT"] = str(settings.mcp_http_port)
    return env


class AmapMCPClient:
    """高德 MCP 服务器（uvx amap-mcp-server）的会话封装：HTTP 默认 / stdio 可选。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        # HTTP 传输时：我们自己起的那个独立服务器进程，以及它 stdout+stderr 的落盘句柄
        self._server_proc: subprocess.Popen | None = None
        self._server_log = None
        # stdio 传输时：mcp 库用的 errlog 句柄
        self._errlog = None
        self._lock = asyncio.Lock()
        # 工具名 -> mcp.types.Tool
        self.tools: dict[str, Any] = {}

    def _subprocess_env(self) -> dict[str, str]:
        """实例方法只是转调模块级函数，保持单一实现。"""

        return build_subprocess_env(self._settings)

    # ------------------------------------------------------------------ 日志与提示
    def _stderr_log(self):
        """把子进程 stderr 落到文件：uvicorn 下启动失败的报错会消失，只剩 "Connection closed"。"""

        LOG_DIR.mkdir(exist_ok=True)
        return SERVER_LOG.open("a", encoding="utf-8", buffering=1)

    def _open_server_log(self):
        LOG_DIR.mkdir(exist_ok=True)
        self._server_log = SERVER_LOG.open("a", encoding="utf-8", buffering=1)
        return self._server_log

    def _close_server_log(self) -> None:
        if self._server_log is not None:
            try:
                self._server_log.close()
            except Exception:  # pragma: no cover
                pass
            finally:
                self._server_log = None

    @staticmethod
    def server_log_tail(lines: int = 14) -> str:
        """服务器日志尾部，失败时带进错误信息。"""

        if not SERVER_LOG.is_file():
            return "（没有日志文件）"
        content = [
            line.rstrip()
            for line in SERVER_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip()
        ]
        if not content:
            return "（日志为空）"
        return "\n".join("    " + line[:200] for line in content[-lines:])

    @staticmethod
    def _hint(message: str) -> str:
        """错误信息 + 一行排查入口（详细自检交给 python -m app.preflight）。"""

        return f"{message}\n排查：python -m app.preflight（同一份配置跑一次握手自检并打印服务器日志）"

    # ------------------------------------------------------------------ 生命周期
    async def start(self) -> None:
        """启动服务器并握手（幂等），按 MCP_TRANSPORT 选 HTTP 或 stdio。失败抛 MCPUnavailable。"""

        if self._session is not None:
            return
        async with self._lock:
            if self._session is not None:
                return

            transport = (self._settings.mcp_transport or TRANSPORT_HTTP).strip().lower()
            if transport == TRANSPORT_HTTP:
                await self._start_http()
            else:
                await self._start_stdio()

            logger.info(
                "MCP 就绪（%s）：%d 个工具：%s",
                transport,
                len(self.tools),
                ", ".join(sorted(self.tools)),
            )

            missing = REQUIRED_TOOLS - set(self.tools)
            if missing:
                await self.aclose()
                raise MCPUnavailable(
                    f"MCP 缺少必需工具 {sorted(missing)}；实际可用={sorted(self.tools)}"
                )

    async def _start_http(self) -> None:
        """把服务器起成独立进程，协议走 HTTP，不建管道。"""

        settings = self._settings
        url = f"http://{settings.mcp_http_host}:{settings.mcp_http_port}/mcp"
        command = [settings.mcp_command, *settings.mcp_arg_list, "streamable-http"]
        env = build_subprocess_env(settings)

        logger.info("启动 MCP 服务器（HTTP）：%s -> %s", " ".join(command), url)

        log = self._open_server_log()
        try:
            # stdin/stdout/stderr 全用 DEVNULL / 文件，不建管道
            self._server_proc = subprocess.Popen(  # noqa: S603 - 命令来自本地配置
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                env=env,
                cwd=str(Path(__file__).resolve().parents[1]),
            )
        except FileNotFoundError as exc:
            self._close_server_log()
            raise MCPUnavailable(
                self._hint(
                    f"找不到命令 `{command[0]}`：{exc}\n"
                    "（检查 MCP_COMMAND / MCP_ARGS，用 uvx 时应为 uvx + amap-mcp-server）"
                ),
                cause=exc,
            ) from exc

        ready, reason = await self._await_server_ready(
            settings.mcp_http_host, settings.mcp_http_port, settings.mcp_start_timeout
        )
        if not ready:
            tail = self.server_log_tail()
            await self.aclose()
            raise MCPUnavailable(
                self._hint(f"MCP HTTP 服务器未就绪：{reason}\n服务器日志尾部：\n{tail}")
            )
        logger.info("MCP 服务器已监听 %s，开始握手…", url)

        stack = AsyncExitStack()
        try:
            read_stream, write_stream, _ = await stack.enter_async_context(
                streamablehttp_client(url)
            )
            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
            listed = await session.list_tools()
        except Exception as exc:
            await stack.aclose()
            tail = self.server_log_tail()
            await self.aclose()
            raise MCPUnavailable(
                self._hint(f"MCP HTTP 握手失败：{exc}\n服务器日志尾部：\n{tail}"), cause=exc
            ) from exc

        self._stack = stack
        self._session = session
        self.tools = {tool.name: tool for tool in listed.tools}

    async def _start_stdio(self) -> None:
        settings = self._settings
        params = StdioServerParameters(
            command=settings.mcp_command,
            args=settings.mcp_arg_list,
            # 继承 os.environ，否则子进程找不到 PATH 上的 uvx
            env=self._subprocess_env(),
        )
        logger.info("启动 MCP 服务器（stdio）：%s %s", params.command, " ".join(params.args or []))

        stack = AsyncExitStack()
        self._errlog = self._stderr_log()
        try:
            read_stream, write_stream = await stack.enter_async_context(
                stdio_client(params, errlog=self._errlog)
            )
            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
            listed = await session.list_tools()
        except Exception as exc:  # 启动/握手/列工具任何一步失败
            await stack.aclose()
            self._close_errlog()
            raise MCPUnavailable(
                self._hint(
                    f"MCP stdio 启动或握手失败：{exc}\n"
                    f"服务器日志尾部：\n{self.server_log_tail()}\n"
                    "本机 stdio 会被沙箱拒绝（[WinError 5]），建议用 MCP_TRANSPORT=http。"
                ),
                cause=exc,
            ) from exc

        self._stack = stack
        self._session = session
        self.tools = {tool.name: tool for tool in listed.tools}

    async def _await_server_ready(
        self, host: str, port: int, timeout: float
    ) -> tuple[bool, str]:
        """等服务器监听端口，同时监视子进程：子进程一退出就立刻失败并带出退出码，
        避免服务器起不来时父进程静默等满超时。
        """

        started = time.monotonic()
        deadline = started + max(1.0, timeout)
        last_report = started

        while time.monotonic() < deadline:
            proc = self._server_proc
            if proc is not None and proc.poll() is not None:
                return (
                    False,
                    f"服务器进程已退出（退出码 {proc.returncode}，"
                    f"耗时 {time.monotonic() - started:.1f}s）",
                )

            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port), timeout=1.0
                )
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:  # pragma: no cover
                    pass
                return True, f"监听成功（耗时 {time.monotonic() - started:.1f}s）"
            except Exception:
                pass

            # 每 5 秒报一次进度，避免"看起来卡死"
            if time.monotonic() - last_report >= 5:
                last_report = time.monotonic()
                logger.info(
                    "等待 MCP 服务器监听 %s:%s …（已 %.0fs，子进程存活=%s）",
                    host,
                    port,
                    time.monotonic() - started,
                    proc is not None and proc.poll() is None,
                )

            await asyncio.sleep(0.3)

        return False, f"{timeout}s 内没有监听 {host}:{port}（子进程仍存活）"

    def _close_errlog(self) -> None:
        if self._errlog is not None:
            try:
                self._errlog.close()
            except Exception:  # pragma: no cover - 关闭失败无需影响主流程
                pass
            finally:
                self._errlog = None

    async def aclose(self) -> None:
        if self._stack is not None:
            try:
                await self._stack.aclose()
            finally:
                self._stack = None
                self._session = None
                self.tools = {}

        # HTTP 传输：收掉服务器进程，否则下次启动端口被占
        proc = self._server_proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                await asyncio.to_thread(proc.wait, 5)
            except Exception:
                try:
                    proc.kill()
                except Exception:  # pragma: no cover
                    pass
        self._server_proc = None
        self._close_server_log()
        self._close_errlog()

    # ------------------------------------------------------------------ 调用
    async def call(self, name: str, arguments: dict[str, Any]) -> str:
        """调用一个 MCP 工具，返回文本结果。会话缺失时先重连一次；
        工具名不存在或调用失败一律抛 MCPUnavailable，由编排器决定是否降级。
        """

        if self._session is None:
            await self.start()

        if name not in self.tools:
            raise MCPUnavailable(
                f"未注册的 MCP 工具 {name}；可用={sorted(self.tools)}"
            )

        try:
            result = await self._session.call_tool(name, arguments)  # type: ignore[union-attr]
        except Exception as exc:
            raise MCPUnavailable(f"MCP 工具 {name} 调用失败：{exc}", cause=exc) from exc

        chunks: list[str] = []
        for item in result.content or []:
            chunks.append(getattr(item, "text", None) or str(item))
        return "\n".join(chunks)

    # ------------------------------------------------------------------ 提示词辅助
    def describe_tools(self, only: set[str] | None = None) -> str:
        """把真实注册的工具名与参数生成给模型看，避免模型凭记忆编造工具名。"""

        lines: list[str] = []
        for name in sorted(self.tools):
            if only is not None and name not in only:
                continue
            tool = self.tools[name]
            schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {}
            properties: dict[str, Any] = schema.get("properties", {}) or {}
            required = set(schema.get("required", []) or [])
            params = ", ".join(
                f"{param}{'' if param in required else '?'}" for param in properties
            ) or "无参数"
            description = (getattr(tool, "description", "") or "").strip().split("\n")[0]
            lines.append(f"- {name}({params}): {description}")
        return "\n".join(lines) if lines else "（当前没有可用工具）"

    def health(self) -> dict[str, Any]:
        """给 /internal/v1/health 用的真实状态（含当前传输方式）。"""

        return {
            "transport": (self._settings.mcp_transport or "stdio"),
            "tools": len(self.tools),
            "required_missing": sorted(REQUIRED_TOOLS - set(self.tools)),
            "available": sorted(self.tools),
        }
