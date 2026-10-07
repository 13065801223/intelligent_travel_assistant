#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冻结契约检查器（M0）。

校验 trip-plan 的请求 / 响应 JSON 是否符合
`docs/backend-dev-guide.md` 第 3 节与附录 A 的冻结契约。
**零第三方依赖，仅标准库。**

这是一个**独立的防漂移工具**，不接入任何运行时请求链路：
- 未来 Java BFF 侧：把 DTO 往返序列化结果喂给它，证明键集合与可空性未漂移；
- Python Agent 侧：把生成的行程喂给它，证明输出契约未漂移。

用法::

    python tools/check_contract.py contracts/trip-plan.sample.json
    python tools/check_contract.py --kind request contracts/trip-plan.request.sample.json
    python tools/check_contract.py --kind plan agent_plan.json    # Agent 内部 API 的裸 TripPlan
    python tools/check_contract.py --keys contracts/trip-plan.sample.json

退出码：0 = 通过；1 = 存在违规；2 = 用法或读取错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MEAL_TYPES = {"breakfast", "lunch", "dinner", "snack"}

# ---------------------------------------------------------------- 冻结契约定义
# 每个节点的 required / optional 即附录 A 的字段表；optional 一律允许 null。
# why 用于把违规与"前端为什么会炸"绑在一起，便于排障。

PLAN_SPEC = {
    "required": {
        "city": str,
        "start_date": str,
        "end_date": str,
        "days": list,
        "overall_suggestions": str,
    },
    "optional": {"weather_info": list, "budget": dict},
    "why": {
        "city": "模板直接渲染 tripPlan.city",
        "start_date": "模板直接渲染 start_date / end_date",
        "end_date": "模板直接渲染 start_date / end_date",
        "days": "Result.vue:433/824 直接 .forEach，无判空 → 绝不能是 null",
        "overall_suggestions": "模板直接渲染（未判空）",
    },
}

DAY_SPEC = {
    "required": {
        "date": str,
        "day_index": int,
        "description": str,
        "transportation": str,
        "accommodation": str,
        "attractions": list,
        "meals": list,
    },
    "optional": {"hotel": dict},
    "why": {
        "date": "模板渲染 day.date",
        "day_index": "Result.vue:54 用 day_index + 1 显示天数，必须 0 起",
        "description": "模板渲染 day.description",
        "transportation": "模板渲染 day.transportation",
        "accommodation": "模板渲染 day.accommodation",
        "attractions": "Result.vue:434/824 直接 .forEach，无判空 → 绝不能是 null",
        "meals": "Result.vue:245 直接 v-for",
    },
}

ATTRACTION_SPEC = {
    "required": {
        "name": str,
        "address": str,
        "visit_duration": int,
        "description": str,
    },
    "optional": {
        # location 允许缺失/为 null：模型可能拿不到坐标，而前端打点是判空的
        # （Result.vue:825）。有坐标时仍必须是数值，见 _check_location。
        "location": dict,
        "category": str,
        "rating": (int, float),
        "photos": list,
        "poi_id": str,
        "image_url": str,
        "ticket_price": int,
    },
    "why": {
        "name": "模板渲染 item.name，并作为图片查询 key",
        "address": "模板渲染 item.address",
        "visit_duration": "模板渲染 item.visit_duration",
        "description": "模板渲染 item.description",
    },
}

MEAL_SPEC = {
    "required": {"type": str, "name": str},
    "optional": {
        "address": str,
        "location": dict,
        "description": str,
        "estimated_cost": int,
    },
    "why": {
        "type": "getMealLabel(meal.type)，取值 breakfast/lunch/dinner/snack",
        "name": "模板渲染 meal.name",
    },
}

HOTEL_SPEC = {
    "required": {"name": str},
    "optional": {
        "address": str,
        "location": dict,
        "price_range": str,
        "rating": str,
        "distance": str,
        "type": str,
        "estimated_cost": int,
    },
    "why": {
        "name": "模板渲染 hotel.name",
        # rating 冻结为字符串（附录 A）：模板渲染 {{ rating }}⭐
        "rating": "冻结契约为字符串（LLM 提示词示例为 \"4.5\"）",
    },
}

WEATHER_SPEC = {
    "required": {
        "date": str,
        "day_weather": str,
        "night_weather": str,
        "day_temp": int,
        "night_temp": int,
        "wind_direction": str,
        "wind_power": str,
    },
    "optional": {},
    "why": {
        "date": "模板渲染 item.date",
        "day_temp": "Result.vue:270 渲染 {{ item.day_temp }}°C，必须纯数字",
        "night_temp": "Result.vue:277 渲染 {{ item.night_temp }}°C，必须纯数字",
    },
}

LOCATION_KEYS = ("longitude", "latitude")


class Report:
    """收集违规（fail）与提示（warn）。"""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def fail(self, path: str, msg: str) -> None:
        self.errors.append(f"{path}: {msg}")

    def warn(self, path: str, msg: str) -> None:
        self.warnings.append(f"{path}: {msg}")


# ---------------------------------------------------------------- 基础类型检查

def _type_name(typ: Any) -> str:
    if isinstance(typ, tuple):
        return "|".join(t.__name__ for t in typ)
    return typ.__name__


def _check_type(rep: Report, path: str, value: Any, typ: Any, why: str = "") -> bool:
    """类型断言。int 与 bool 在 JSON/Python 中易混，这里显式排除 bool。"""
    ok = isinstance(value, typ)
    if ok and typ in (int, (int, float)) and isinstance(value, bool):
        ok = False
    if ok and isinstance(typ, tuple) and int in typ and isinstance(value, bool):
        ok = False
    if not ok:
        suffix = f"（{why}）" if why else ""
        rep.fail(
            path,
            f"期望 {_type_name(typ)}，实际 {type(value).__name__} = {value!r}{suffix}",
        )
    return ok


def _check_node(rep: Report, path: str, obj: dict, spec: dict) -> None:
    why = spec.get("why", {})
    for key, typ in spec["required"].items():
        if key not in obj:
            rep.fail(f"{path}.{key}", f"缺失（{why.get(key, '契约必填')}）")
            continue
        if obj[key] is None:
            rep.fail(f"{path}.{key}", f"为 null，但契约要求 {_type_name(typ)}（{why.get(key, '必填')}）")
            continue
        _check_type(rep, f"{path}.{key}", obj[key], typ, why.get(key, ""))
    for key, typ in spec["optional"].items():
        if key in obj and obj[key] is not None:
            _check_type(rep, f"{path}.{key}", obj[key], typ, why.get(key, ""))
    extras = sorted(set(obj) - set(spec["required"]) - set(spec["optional"]))
    if extras:
        rep.warn(path, "包含未在冻结契约中的字段（会被 BFF 忽略）：" + ", ".join(extras))


def _check_location(rep: Report, path: str, obj: Any) -> None:
    if not isinstance(obj, dict):
        return
    for key in LOCATION_KEYS:
        if key not in obj:
            rep.fail(f"{path}.{key}", "缺失（Result.vue:825 地图打点需要经纬度）")
        elif not isinstance(obj[key], (int, float)) or isinstance(obj[key], bool):
            rep.fail(
                f"{path}.{key}",
                f"期望 number，实际 {type(obj[key]).__name__}（地图打点需要数值）",
            )


def _check_date(rep: Report, path: str, value: Any) -> None:
    if isinstance(value, str) and not DATE_RE.match(value):
        rep.warn(path, f"不是 YYYY-MM-DD 格式：{value!r}（前端仅原样显示，故记为提示）")


# ---------------------------------------------------------------- 响应校验

def validate_response(doc: Any) -> Report:
    rep = Report()
    if not isinstance(doc, dict):
        rep.fail("$", f"响应根必须是 object，实际 {type(doc).__name__}")
        return rep

    for key in ("success", "message", "data"):
        if key not in doc:
            rep.fail(key, "缺失（前端读取 response.success / response.message）")
    if "success" in doc and not isinstance(doc["success"], bool):
        rep.fail(
            "success",
            f"期望 bool，实际 {type(doc['success']).__name__}（Home.vue:297 用它判断成败）",
        )
    if "message" in doc and not isinstance(doc["message"], str):
        rep.fail("message", f"期望 string，实际 {type(doc['message']).__name__}")

    data = doc.get("data")
    if data is None:
        return rep
    if not isinstance(data, dict):
        rep.fail("data", f"期望 object|null，实际 {type(data).__name__}")
        return rep

    _check_node(rep, "data", data, PLAN_SPEC)
    _check_date(rep, "data.start_date", data.get("start_date"))
    _check_date(rep, "data.end_date", data.get("end_date"))

    # days
    days = data.get("days")
    if isinstance(days, list):
        if not days:
            rep.warn("data.days", "为空数组：前端可以渲染但页面无内容")
        for i, day in enumerate(days):
            dpath = f"data.days[{i}]"
            if not isinstance(day, dict):
                rep.fail(dpath, f"期望 object，实际 {type(day).__name__}")
                continue
            _check_node(rep, dpath, day, DAY_SPEC)
            _check_date(rep, f"{dpath}.date", day.get("date"))
            hotel = day.get("hotel")
            if isinstance(hotel, dict):
                _check_node(rep, f"{dpath}.hotel", hotel, HOTEL_SPEC)
                _check_location(rep, f"{dpath}.hotel.location", hotel.get("location"))
            attractions = day.get("attractions")
            if isinstance(attractions, list):
                if not attractions:
                    rep.warn(f"{dpath}.attractions", "为空数组")
                for j, attr in enumerate(attractions):
                    apath = f"{dpath}.attractions[{j}]"
                    if not isinstance(attr, dict):
                        rep.fail(apath, f"期望 object，实际 {type(attr).__name__}")
                        continue
                    _check_node(rep, apath, attr, ATTRACTION_SPEC)
                    _check_location(rep, f"{apath}.location", attr.get("location"))
            meals = day.get("meals")
            if isinstance(meals, list):
                if not meals:
                    rep.warn(f"{dpath}.meals", "为空数组")
                for j, meal in enumerate(meals):
                    mpath = f"{dpath}.meals[{j}]"
                    if not isinstance(meal, dict):
                        rep.fail(mpath, f"期望 object，实际 {type(meal).__name__}")
                        continue
                    _check_node(rep, mpath, meal, MEAL_SPEC)
                    if meal.get("type") not in MEAL_TYPES:
                        rep.fail(
                            f"{mpath}.type",
                            f"取值 {meal.get('type')!r} 不在 {sorted(MEAL_TYPES)} 内"
                            "（getMealLabel 依赖该取值）",
                        )
                    _check_location(rep, f"{mpath}.location", meal.get("location"))

        # day_index 必须构成 0..n-1 的完整集合：前端用 day_index+1 显示"第 N 天"
        indices = [
            d.get("day_index") for d in days if isinstance(d, dict)
        ]
        if all(isinstance(v, int) and not isinstance(v, bool) for v in indices) and indices:
            if sorted(indices) != list(range(len(indices))):
                rep.fail(
                    "data.days[].day_index",
                    f"应构成 0..{len(indices) - 1} 的完整集合（0 起），实际 {sorted(indices)}"
                    "（Result.vue:54 用 day_index + 1 显示天数）",
                )

    # weather_info
    weather = data.get("weather_info")
    if isinstance(weather, list):
        for i, w in enumerate(weather):
            wpath = f"data.weather_info[{i}]"
            if not isinstance(w, dict):
                rep.fail(wpath, f"期望 object，实际 {type(w).__name__}")
                continue
            _check_node(rep, wpath, w, WEATHER_SPEC)

    # budget
    budget = data.get("budget")
    if isinstance(budget, dict):
        for key in (
            "total_attractions",
            "total_hotels",
            "total_meals",
            "total_transportation",
            "total",
        ):
            if key in budget and budget[key] is not None:
                _check_type(rep, f"data.budget.{key}", budget[key], int, "模板渲染 ¥{{ }}")
        extras = sorted(
            set(budget)
            - {
                "total_attractions",
                "total_hotels",
                "total_meals",
                "total_transportation",
                "total",
            }
        )
        if extras:
            rep.warn("data.budget", "包含未在冻结契约中的字段：" + ", ".join(extras))

    return rep


def validate_plan(doc: Any) -> Report:
    """校验**裸 TripPlan**（Agent 服务内部 API 的返回体，没有 {success,message,data} 外壳）。

    实现上复用响应校验：把裸对象临时包进外壳，再把报告里的路径前缀 `data.` 改写成
    `plan.`。这样错误信息仍然直观，也避免维护两套重复的校验逻辑。
    """

    rep = validate_response({"success": True, "message": "", "data": doc})
    renamed = Report()
    renamed.errors = [
        item.replace("data.", "plan.", 1).replace("data:", "plan:", 1)
        for item in rep.errors
    ]
    renamed.warnings = [
        item.replace("data.", "plan.", 1).replace("data:", "plan:", 1)
        for item in rep.warnings
    ]
    return renamed


# ---------------------------------------------------------------- 请求校验

def validate_request(doc: Any) -> Report:
    rep = Report()
    if not isinstance(doc, dict):
        rep.fail("$", f"请求根必须是 object，实际 {type(doc).__name__}")
        return rep

    for key in ("city", "start_date", "end_date", "transportation", "accommodation"):
        if key not in doc:
            rep.fail(key, "缺失（TripFormData 必填）")
        elif not isinstance(doc[key], str):
            rep.fail(key, f"期望 string，实际 {type(doc[key]).__name__}")
        elif key in ("city", "transportation", "accommodation") and not doc[key].strip():
            rep.fail(key, "为空字符串（Pydantic 侧为必填字段）")

    for key in ("start_date", "end_date"):
        value = doc.get(key)
        if isinstance(value, str) and value and not DATE_RE.match(value):
            rep.fail(key, f"必须是 YYYY-MM-DD，实际 {value!r}")

    if "travel_days" not in doc:
        rep.fail("travel_days", "缺失（TripFormData 必填）")
    else:
        days = doc["travel_days"]
        if not isinstance(days, int) or isinstance(days, bool):
            rep.fail("travel_days", f"期望 int，实际 {type(days).__name__}")
        elif not 1 <= days <= 30:
            rep.fail("travel_days", f"必须在 1..30，实际 {days}（= Pydantic ge=1 le=30）")

    if "preferences" in doc and doc["preferences"] is not None:
        prefs = doc["preferences"]
        if not isinstance(prefs, list) or any(not isinstance(p, str) for p in prefs):
            rep.fail("preferences", "期望 string 数组")

    if "free_text_input" in doc and doc["free_text_input"] is not None:
        if not isinstance(doc["free_text_input"], str):
            rep.fail("free_text_input", "期望 string|null")

    extras = sorted(
        set(doc)
        - {
            "city",
            "start_date",
            "end_date",
            "travel_days",
            "transportation",
            "accommodation",
            "preferences",
            "free_text_input",
        }
    )
    if extras:
        rep.warn("$", "包含未在冻结契约中的请求字段：" + ", ".join(extras))

    return rep


# ---------------------------------------------------------------- 入口

def detect_kind(doc: Any) -> str:
    if isinstance(doc, dict):
        if "success" in doc or "data" in doc:
            return "response"
        if "city" in doc and "travel_days" in doc:
            return "request"
        if "city" in doc and "days" in doc:
            return "plan"
    raise ValueError("无法自动识别类型：请用 --kind request|response|plan 显式指定")


def validate_document(doc: Any, kind: str | None = None) -> tuple[str, Report]:
    resolved = kind or detect_kind(doc)
    if resolved == "response":
        return resolved, validate_response(doc)
    if resolved == "request":
        return resolved, validate_request(doc)
    if resolved == "plan":
        return resolved, validate_plan(doc)
    raise ValueError(f"未知类型：{resolved}")


def flatten_paths(obj: Any, prefix: str = "") -> list[str]:
    """展开键路径，用于跨语言键集合比对。

    **容器路径也会输出**：`days 必须存在且是数组`、`days[].attractions`、
    `days[].hotel` 这些"字段/对象是否存在"本身就是契约红线，只输出叶子会让它们消失。
    列表元素折叠为 []（空列表只留字段路径本身）。
    """
    out: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key in sorted(node):
                child = f"{path}.{key}" if path else key
                out.append(child)
                walk(node[key], child)
        elif isinstance(node, list):
            if node:
                walk(node[0], f"{path}[]")

    walk(obj, prefix)
    return out


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"[ERR] 文件不存在：{path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[ERR] JSON 解析失败：{path}\n      {exc}")
    except UnicodeDecodeError as exc:
        raise SystemExit(f"[ERR] 编码不是 UTF-8：{path}\n      {exc}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="冻结契约检查器（M0，零依赖）")
    parser.add_argument("path", help="要检查的 JSON 文件")
    parser.add_argument(
        "--kind",
        choices=["request", "response", "plan"],
        default=None,
        help="request=请求体；response=完整响应外壳；plan=裸 TripPlan（Agent 内部 API）",
    )
    parser.add_argument(
        "--keys", action="store_true", help="只打印扁平键路径（供跨语言键集合比对）"
    )
    parser.add_argument("--quiet", action="store_true", help="仅输出结论")
    args = parser.parse_args(argv)

    target = Path(args.path)
    doc = load_json(target)

    if args.keys:
        for path in flatten_paths(doc):
            print(path)
        return 0

    kind, rep = validate_document(doc, args.kind)
    if not args.quiet:
        for item in rep.errors:
            print(f"[FAIL] {item}")
        for item in rep.warnings:
            print(f"[WARN] {item}")

    status = "PASS" if not rep.errors else "FAIL"
    print(
        f"{status}  {target.name}  kind={kind}  "
        f"violations={len(rep.errors)}  warnings={len(rep.warnings)}"
    )
    return 0 if not rep.errors else 1


if __name__ == "__main__":
    sys.exit(main())
