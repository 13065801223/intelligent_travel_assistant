# -*- coding: utf-8 -*-
"""多智能体编排：景点 → 天气 → 酒店 → 行程规划。

- 前三个 Agent 并行（互不依赖）；
- 解析失败抛 PlanParseFailed，不做"编造行程"兜底；
- 软失败：MCP 不可用 → 记"未获取到"并继续，在 overall_suggestions 里说明；
- 硬失败：LLM 超时/报错、超预算、JSON 不合契约 → 抛错，由 BFF 翻成 504/502。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Awaitable, Callable

from .agent_loop import PlainAgent, ToolAgent
from .agents import (
    ATTRACTION_AGENT_PROMPT,
    HOTEL_AGENT_PROMPT,
    PLANNER_AGENT_PROMPT,
    WEATHER_AGENT_PROMPT,
)
from .config import Settings
from .errors import DeadlineExceeded, MCPUnavailable, PlanParseFailed
from .llm import LLMClient
from .mcp_client import AmapMCPClient
from .schemas import Location, TripPlan, TripRequest
from .tools_amap import AmapTools

logger = logging.getLogger(__name__)

# 实时数据缺失时的占位（明确告知模型"没有实时数据"，而不是留空）
NOT_AVAILABLE = "（未获取到实时数据：高德 MCP 本次不可用）"

DEGRADED_NOTICE = (
    "（提示：本次未能获取到部分实时数据，以下行程为综合建议，"
    "景点开放时间、天气与酒店价格请出行前自行核对。）"
)

# 坐标补齐的候选上限（防跑飞：4 天 ×(2~3 景点 + 1 酒店) 很容易超过 8）
MAX_GEOCODE_TARGETS = 32
# 单个点的 maps_geo 尝试次数（地址 / 搜到的真名 / 模型给的名字 / 去掉分店括号的名字）
MAX_GEOCODE_ATTEMPTS_PER_TARGET = 4

# 高德返回里的坐标：`"location": "120.493792,30.741511"`（经度在前）
_GEO_LOCATION_RE = re.compile(r'"location"\s*:\s*"([\d.]+),([\d.]+)"')
# 分店括号："汉庭酒店(嘉兴南湖店)" -> "汉庭酒店"
_BRANCH_PAREN_RE = re.compile(r"[（(][^）)]*[）)]")


def parse_geo_location(text: str) -> Location | None:
    """从 maps_geo 的原始返回里取坐标；取不到（含高德的 error 体）就返回 None。"""

    match = _GEO_LOCATION_RE.search(text or "")
    if not match:
        return None
    return Location(longitude=float(match.group(1)), latitude=float(match.group(2)))


def _names(targets: list[Any]) -> str:
    """把目标点列成人能读的一行，用于日志里点名。"""

    return "、".join(
        (getattr(t, "name", "") or "（无名）") for t in targets
    ) or "（无）"


def _poi_names(text: str) -> list[str]:
    """从 maps_text_search 的返回里取出 POI 名字（按相关性顺序）。

    该工具的 POI 只有 id/name/address/typecode，**拿不到坐标**；坐标仍得靠 maps_geo。
    """

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    pois = data.get("pois") or []
    names: list[str] = []
    for poi in pois:
        if isinstance(poi, dict) and poi.get("name"):
            names.append(str(poi["name"]))
    return names


def extract_json(text: str) -> dict[str, Any]:
    """从模型输出里抠出 JSON 对象（```json 代码块 → 任意代码块 → 首尾花括号）。

    解析失败显式抛错，不退化成"编造行程"。
    """

    source = text or ""
    if "```json" in source:
        start = source.find("```json") + len("```json")
        end = source.find("```", start)
        raw = source[start:end].strip()
    elif "```" in source:
        start = source.find("```") + 3
        end = source.find("```", start)
        raw = source[start:end].strip()
    elif "{" in source and "}" in source:
        raw = source[source.find("{") : source.rfind("}") + 1]
    else:
        raise PlanParseFailed("行程 Agent 的输出里找不到 JSON")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PlanParseFailed(f"行程 JSON 解析失败：{exc}") from exc

    if not isinstance(data, dict):
        raise PlanParseFailed(f"行程 JSON 顶层必须是对象，实际 {type(data).__name__}")
    return data


class TripPlanner:
    """一次请求创建一个实例也可以；这里由 main.py 常驻复用（无状态）。"""

    def __init__(self, settings: Settings, llm: LLMClient, mcp: AmapMCPClient) -> None:
        self._settings = settings
        self._mcp = mcp
        tools = AmapTools(mcp).registry()

        # 三个工具 Agent：各自只看到自己需要的那个工具（收窄提示词）
        self._attraction_agent = ToolAgent(
            "景点搜索专家", ATTRACTION_AGENT_PROMPT, llm, tools, settings,
            lambda: mcp.describe_tools({"maps_text_search"}),
        )
        self._weather_agent = ToolAgent(
            "天气查询专家", WEATHER_AGENT_PROMPT, llm, tools, settings,
            lambda: mcp.describe_tools({"maps_weather"}),
        )
        self._hotel_agent = ToolAgent(
            "酒店推荐专家", HOTEL_AGENT_PROMPT, llm, tools, settings,
            lambda: mcp.describe_tools({"maps_text_search"}),
        )
        # 行程 Agent 是"整合者"，不需要工具
        self._planner_agent = PlainAgent("行程规划专家", PLANNER_AGENT_PROMPT, llm)

    # ------------------------------------------------------------- 查询构造
    @staticmethod
    def _attraction_query(request: TripRequest) -> str:
        keyword = request.preferences[0] if request.preferences else "景点"
        # 把工具调用格式写进 query：强制模型第一步就调工具
        return (
            f"请使用 maps_text_search 工具搜索{request.city}的{keyword}相关景点。\n"
            f"[TOOL_CALL:maps_text_search:keywords={keyword},city={request.city}]"
        )

    @staticmethod
    def _weather_query(request: TripRequest) -> str:
        return f"请查询{request.city}的天气信息"

    @staticmethod
    def _hotel_query(request: TripRequest) -> str:
        return f"请搜索{request.city}的{request.accommodation}酒店"

    @staticmethod
    def _planner_query(
        request: TripRequest, attractions: str, weather: str, hotels: str
    ) -> str:
        query = f"""请根据以下信息生成{request.city}的{request.travel_days}天旅行计划:

**基本信息:**
- 城市: {request.city}
- 日期: {request.start_date} 至 {request.end_date}
- 天数: {request.travel_days}天
- 交通方式: {request.transportation}
- 住宿: {request.accommodation}
- 偏好: {', '.join(request.preferences) if request.preferences else '无'}

**景点信息:**
{attractions}

**天气信息:**
{weather}

**酒店信息:**
{hotels}

**要求:**
1. 每天安排2-3个景点
2. 每天必须包含早中晚三餐
3. 每天推荐一个具体的酒店(从酒店信息中选择)
4. 考虑景点之间的距离和交通方式
5. 返回完整的JSON格式数据
6. 景点的经纬度坐标要真实准确
7. day_index 从 0 开始
"""
        if request.free_text_input:
            query += f"\n**额外要求:** {request.free_text_input}"
        return query

    # ------------------------------------------------------------- 主流程
    async def plan(self, request: TripRequest) -> TripPlan:
        started = time.monotonic()
        deadline = started + self._settings.agent_deadline_seconds
        logger.info(
            "开始规划：%s %s→%s 共 %d 天（时间预算 %ds）",
            request.city, request.start_date, request.end_date,
            request.travel_days, self._settings.agent_deadline_seconds,
        )

        # 步骤 1~3：检索类 Agent 并行
        labels = ("景点", "天气", "酒店")
        gathered = await asyncio.gather(
            self._attraction_agent.run(self._attraction_query(request)),
            self._weather_agent.run(self._weather_query(request)),
            self._hotel_agent.run(self._hotel_query(request)),
            return_exceptions=True,
        )

        texts: list[str] = []
        degraded = False
        for label, item in zip(labels, gathered):
            if isinstance(item, BaseException):
                if isinstance(item, MCPUnavailable):
                    logger.warning("[%s] 实时数据不可用，降级继续：%s", label, item)
                    texts.append(NOT_AVAILABLE)
                    degraded = True
                    continue
                # LLM 超时/报错等一律硬失败
                raise item
            texts.append(item)

        self._check_deadline(deadline, "并行检索阶段")
        attractions, weather, hotels = texts
        logger.info(
            "检索阶段完成，耗时 %.1fs（降级=%s）", time.monotonic() - started, degraded
        )

        # 步骤 4：行程规划 Agent 汇总
        planner_text = await self._planner_agent.run(
            self._planner_query(request, attractions, weather, hotels)
        )
        self._check_deadline(deadline, "行程生成阶段")

        data = extract_json(planner_text)
        try:
            plan = TripPlan.model_validate(data)
        except Exception as exc:
            raise PlanParseFailed(f"行程不符合冻结契约：{exc}") from exc

        plan = self._normalize(plan, request)
        plan = await self._backfill_coordinates(plan, request)
        if degraded:
            plan = plan.model_copy(
                update={"overall_suggestions": DEGRADED_NOTICE + plan.overall_suggestions}
            )

        logger.info(
            "规划完成：%d 天，总耗时 %.1fs", len(plan.days), time.monotonic() - started
        )
        return plan

    async def _backfill_coordinates(
        self,
        plan: TripPlan,
        request: TripRequest,
        search: Callable[[str], Awaitable[list[str]]] | None = None,
    ) -> TripPlan:
        """用高德 maps_geo 把缺失的经纬度补真（模型常把坐标写成 null）。坐标必须是真实数据，
        不编造；有界执行（见 MAX_GEOCODE_TARGETS / MAX_GEOCODE_ATTEMPTS_PER_TARGET）。

        三条边界：
        1. 只要有 name 或 address 就是候选（Hotel.address 默认 ""，不能因此静默跳过）；
        2. 单个点按 [地址 → 搜到的真名 → 模型给的名字 → 去括号的名字] 逐个试
           —— 带分店括号的名字会被高德 engine 拒掉；
        3. 补不上的点要在日志里点名。

        `search` 参数仅供测试注入，默认用真实的 maps_text_search。
        """

        if search is None:
            search = self._search_poi_names

        targets: list[Any] = []
        for day in plan.days:
            if day.hotel is not None and day.hotel.location is None:
                targets.append(day.hotel)
            for attraction in day.attractions:
                if attraction.location is None:
                    targets.append(attraction)

        if not targets:
            return plan

        if "maps_geo" not in self._mcp.tools:
            logger.warning(
                "MCP 无 maps_geo 工具，%d 个缺失坐标无法补齐：%s",
                len(targets),
                _names(targets),
            )
            return plan

        if len(targets) > MAX_GEOCODE_TARGETS:
            dropped = targets[MAX_GEOCODE_TARGETS:]
            logger.warning(
                "缺失坐标 %d 个，超过单次补齐上限 %d，以下 %d 个不补：%s",
                len(targets),
                MAX_GEOCODE_TARGETS,
                len(dropped),
                _names(dropped),
            )
            targets = targets[:MAX_GEOCODE_TARGETS]

        async def geocode(target: Any) -> Location | None:
            for candidate in await self._geo_candidates(target, request, search):
                if candidate in seen:
                    continue
                seen.add(candidate)
                try:
                    text = await self._mcp.call(
                        "maps_geo", {"address": candidate, "city": request.city}
                    )
                except Exception as exc:  # 补齐失败不影响主流程
                    logger.debug("maps_geo(%r) 异常：%s", candidate, exc)
                    continue
                location = parse_geo_location(text)
                if location is not None:
                    logger.debug("maps_geo(%r) 命中 %s", candidate, location)
                    return location
            return None

        seen: set[str] = set()
        results = await asyncio.gather(*(geocode(t) for t in targets), return_exceptions=True)

        filled = 0
        missing: list[Any] = []
        for target, result in zip(targets, results):
            if isinstance(result, Location):
                target.location = result  # Pydantic v2 模型默认可变，直接回填
                filled += 1
            else:
                missing.append(target)
                if isinstance(result, BaseException):
                    logger.debug("坐标补齐异常：%s", result)

        logger.info("坐标补齐：%d/%d 个（高德 maps_geo）", filled, len(targets))
        if missing:
            # 点名补不上的点，而不是只给一个比值
            logger.warning("仍缺坐标 %d 个：%s", len(missing), _names(missing))
        return plan

    async def _geo_candidates(
        self,
        target: Any,
        request: TripRequest,
        search: Callable[[str], Awaitable[list[str]]],
    ) -> list[str]:
        """一个点要试的 maps_geo 查询串：地址优先（省掉一次 maps_text_search），
        地址走不通才去搜真实名字。
        """

        name = (getattr(target, "name", "") or "").strip()
        address = (getattr(target, "address", "") or "").strip()

        candidates: list[str] = [address] if address else []

        if name:
            if "maps_text_search" in self._mcp.tools and len(candidates) < MAX_GEOCODE_ATTEMPTS_PER_TARGET:
                for poi_name in await search(name):
                    if poi_name not in candidates:
                        candidates.append(poi_name)
                    if len(candidates) >= MAX_GEOCODE_ATTEMPTS_PER_TARGET:
                        break
            if name not in candidates:
                candidates.append(name)
            # 分店括号会让高德 engine 报错，去掉再试一次
            stripped = _BRANCH_PAREN_RE.sub("", name).strip()
            if stripped and stripped not in candidates:
                candidates.append(stripped)

        return [c for c in candidates if c][:MAX_GEOCODE_ATTEMPTS_PER_TARGET]

    async def _search_poi_names(self, keyword: str, city: str) -> list[str]:
        """按名字搜 POI 拿真实存在的名字（坐标仍靠 maps_geo）。"""

        try:
            text = await self._mcp.call(
                "maps_text_search", {"keywords": keyword, "city": city}
            )
        except Exception as exc:  # 搜索失败不影响后续候选
            logger.debug("maps_text_search(%r) 失败：%s", keyword, exc)
            return []
        return _poi_names(text)

    # ------------------------------------------------------------- 内部工具
    @staticmethod
    def _check_deadline(deadline: float, stage: str) -> None:
        if time.monotonic() > deadline:
            raise DeadlineExceeded(
                f"{stage}超出时间预算（{int(deadline - time.monotonic())}s 余额）"
            )

    @staticmethod
    def _normalize(plan: TripPlan, request: TripRequest) -> TripPlan:
        """只归一化，不编造内容：

        1. `day_index` 重排为 0..n-1（前端用 day_index+1 显示"第 N 天"，契约闸门也要求 0 起连续）；
        2. `city` / `start_date` / `end_date` 以请求为准（用户输入的事实，不该由模型改写）。
        """

        if not plan.days:
            raise PlanParseFailed("行程 days 为空：模型没有产出任何一天的计划")

        days = [
            day.model_copy(update={"day_index": index})
            for index, day in enumerate(plan.days)
        ]
        if len(days) != request.travel_days:
            logger.warning(
                "模型产出 %d 天，请求为 %d 天（按模型产出返回，不编造补足）",
                len(days), request.travel_days,
            )

        return plan.model_copy(
            update={
                "city": request.city,
                "start_date": request.start_date,
                "end_date": request.end_date,
                "days": days,
            }
        )
