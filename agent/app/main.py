# -*- coding: utf-8 -*-
"""Agent 服务的内部 API（只给 BFF 用：内网、无鉴权、无 CORS）。

| 路由 | 返回 |
|---|---|
| `GET  /internal/v1/health` | LLM 配置 + 真实 MCP 工具数与缺失项 |
| `POST /internal/v1/trip-plan` | 裸 TripPlan（外壳由 BFF 负责） |

`AGENT_MODE=stub` 时不启动 MCP、不调 LLM，直接返回契约黄金样本的 data 部分。

错误约定：非 2xx + {"error": {"code","message","trace_id"}}
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

from .config import settings
from .errors import AgentError, MCPUnavailable, PlanParseFailed
from .llm import LLMClient
from .mcp_client import AmapMCPClient
from .orchestrator import TripPlanner
from .schemas import TripRequest

_LOG_LEVEL = getattr(logging, settings.log_level.upper(), logging.INFO)
logging.basicConfig(
    level=_LOG_LEVEL,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
)
# uvicorn 会先配置 root logger，这里显式设置本包级别，保证服务日志可见
logging.getLogger("app").setLevel(_LOG_LEVEL)
logger = logging.getLogger("app.api")

mcp_client = AmapMCPClient(settings)
llm_client = LLMClient(settings)
planner: TripPlanner | None = None
_stub_payload: dict | None = None


def _load_stub_payload() -> dict:
    """stub 模式复用契约黄金样本，保证与冻结契约逐字节一致。"""

    path = Path(settings.contract_sample)
    if not path.is_file():
        raise PlanParseFailed(f"契约黄金样本不存在：{path}")
    document = json.loads(path.read_text(encoding="utf-8"))
    return document["data"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    global planner, _stub_payload

    if settings.is_stub:
        _stub_payload = _load_stub_payload()
        logger.warning(
            "AGENT_MODE=stub：不启动 MCP、不调用 LLM，直接返回契约黄金样本（零成本联调）"
        )
    else:
        # fail fast：MCP 起不来就别让服务"看起来正常"
        await mcp_client.start()
        planner = TripPlanner(settings, llm_client, mcp_client)
        logger.info(
            "AGENT_MODE=real：MCP 工具 %d 个，模型 %s",
            len(mcp_client.tools), settings.llm_model_id,
        )

    yield

    await mcp_client.aclose()
    await llm_client.aclose()


app = FastAPI(title="智能旅行助手 · Agent 服务", version="1.0.0", lifespan=lifespan)


@app.exception_handler(AgentError)
async def handle_agent_error(request: Request, exc: AgentError) -> JSONResponse:
    trace_id = request.headers.get("X-Trace-Id", "")
    logger.error("[%s] %s: %s", trace_id or "-", exc.code, exc.message)
    return JSONResponse(
        status_code=exc.http_status,
        content={
            "error": {"code": exc.code, "message": exc.message, "trace_id": trace_id}
        },
    )


@app.get("/internal/v1/health")
async def health() -> dict:
    llm_info = {
        "base_url": settings.llm_base_url,
        "model": settings.llm_model_id,
        "timeout": settings.llm_timeout,
    }
    if settings.is_stub:
        return {
            "status": "stub",
            "mode": "stub",
            "llm": llm_info,
            "mcp": {"tools": 0, "required_missing": [], "available": []},
        }

    mcp_info = mcp_client.health()
    return {
        "status": "degraded" if mcp_info["required_missing"] else "ok",
        "mode": "real",
        "llm": llm_info,
        "mcp": mcp_info,
    }


@app.post("/internal/v1/trip-plan")
async def trip_plan(
    request: TripRequest, x_trace_id: str | None = Header(default=None)
) -> JSONResponse:
    """生成行程。返回**裸 TripPlan**，不包 {success,message,data} 外壳。"""

    if x_trace_id:
        logger.info(
            "[%s] 收到规划请求：%s %d 天", x_trace_id, request.city, request.travel_days
        )

    if settings.is_stub:
        if _stub_payload is None:
            raise PlanParseFailed("stub 样本未加载（lifespan 未执行？）")
        return JSONResponse(content=_stub_payload)

    if planner is None:
        raise MCPUnavailable("planner 未初始化：AGENT_MODE=real 但 MCP 未成功启动")

    plan = await planner.plan(request)
    return JSONResponse(content=plan.model_dump(mode="json"))
