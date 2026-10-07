# -*- coding: utf-8 -*-
"""MCP 自检：直接跑真实客户端，成功或失败都给可读报告。

用法：
    python -m app.preflight                # 用 .env 配置
    python -m app.preflight --timeout 180  # 覆盖启动等待秒数

退出码：0 = 握手成功且必需工具齐全；1 = 失败。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from .config import settings
from .errors import MCPUnavailable
from .mcp_client import (
    DEFAULT_UV_CACHE_DIR,
    DEFAULT_UV_TOOL_DIR,
    REQUIRED_TOOLS,
    SERVER_LOG,
    AmapMCPClient,
    _uv_dir,
)


async def check(timeout: int) -> int:
    print("MCP 自检")
    print(f"  传输方式    : {settings.mcp_transport}")
    print(f"  启动命令    : {settings.mcp_command} {' '.join(settings.mcp_arg_list)}")
    if settings.mcp_transport.strip().lower() == "http":
        print(f"  监听地址    : http://{settings.mcp_http_host}:{settings.mcp_http_port}/mcp")
    print(f"  PyPI 索引   : {settings.mcp_uv_index or '未设置（uv 将走 pypi.org；本机实测该索引页要 180s）'}")
    print(f"  uv 缓存目录 : {_uv_dir(settings.mcp_uv_cache_dir, DEFAULT_UV_CACHE_DIR)}")
    print(f"  uv 工具目录 : {_uv_dir(settings.mcp_uv_tool_dir, DEFAULT_UV_TOOL_DIR)}")
    print(f"  高德 key    : 长度 {len(settings.amap_api_key)}（作为 AMAP_MAPS_API_KEY 注入）")
    print(f"  服务器日志  : {SERVER_LOG}")
    print(f"  启动等待    : {timeout}s")
    print()

    client = AmapMCPClient(settings)
    started = time.time()
    try:
        await client.start()
    except MCPUnavailable as exc:
        print(f"结果：❌ 失败（耗时 {time.time() - started:.1f}s）")
        print(str(exc))
        return 1

    print(f"结果：✅ 握手成功（耗时 {time.time() - started:.1f}s）")
    print(f"  工具数      : {len(client.tools)}")
    print(f"  必需工具缺失: {sorted(REQUIRED_TOOLS - set(client.tools)) or '无'}")
    print(f"  可用工具    : {', '.join(sorted(client.tools))}")

    try:
        text = await client.call("maps_weather", {"city": "杭州"})
        print(f"  真实调用    : maps_weather(杭州) -> {text[:110]}".replace("\n", " "))
    except Exception as exc:  # noqa: BLE001 - 自检就是要暴露一切
        print(f"  真实调用    : ❌ {exc}")
    finally:
        await client.aclose()
    return 0


def _force_utf8_output() -> None:
    """把 stdout/stderr 钉成 UTF-8。

    中文 Windows 的输出流是 GBK，报告里的 ✅/❌ 会让**成功**那行崩掉
    （UnicodeEncodeError → exit 1 + traceback）。只在命令行入口调用。
    """

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:  # 非交互/被重定向时可能是普通 file-like
            try:
                reconfigure(encoding="utf-8")
            except Exception:  # pragma: no cover - 尽力而为，绝不因此改变自检结论
                pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    parser = argparse.ArgumentParser(description="MCP 自检（复用真实客户端）")
    parser.add_argument("--timeout", type=int, default=None, help="覆盖 MCP_START_TIMEOUT")
    args = parser.parse_args(argv)
    if args.timeout:
        settings.mcp_start_timeout = args.timeout
    return asyncio.run(check(settings.mcp_start_timeout))


if __name__ == "__main__":
    sys.exit(main())
