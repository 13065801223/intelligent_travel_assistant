# -*- coding: utf-8 -*-
"""冻结契约的 Pydantic 模型 —— 契约 Owner。

BFF 只镜像成 DTO，不复制这里的清洗规则（避免两个 Owner）；漂移由 tools/check_contract.py 把关。

【改字段的规矩】必须同步四处，否则契约闸门会红：
    contracts/trip-plan.sample.json → agent/tests/test_contract.py
    → backend 的 DTO → docs/backend-dev-guide.md 附录 A
"""

from __future__ import annotations

from typing import List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TripRequest(BaseModel):
    """BFF 转发的请求（字段与前端 TripFormData 一致）。用户友好报错由 BFF 负责，这里只做最后一道。"""

    model_config = ConfigDict(extra="ignore")

    city: str = Field(..., description="目的地城市")
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD")
    travel_days: int = Field(..., ge=1, le=30, description="旅行天数")
    transportation: str = Field(..., description="交通方式")
    accommodation: str = Field(..., description="住宿偏好")
    preferences: List[str] = Field(default_factory=list, description="旅行偏好标签")
    free_text_input: Optional[str] = Field(default="", description="额外要求")
    # BFF 透传的追踪号：只进日志，不参与业务
    trace_id: Optional[str] = Field(default=None, description="追踪号（BFF 透传）")


def _coerce_incomplete_location(value):
    """把"半截坐标"折成 None。

    模型对拿不到经纬度的点会输出 `{"longitude": null, "latitude": null}`，直接进 Location
    会校验失败、整条链路 502；前端打点逻辑本来就判空，所以"没有坐标"是可以接受的。
    能补的坐标由 orchestrator 用 maps_geo 补真，补不到就留空（不编造）。
    """

    if value is None:
        return None
    if isinstance(value, dict):
        longitude, latitude = value.get("longitude"), value.get("latitude")

        def numeric(v):
            return isinstance(v, (int, float)) and not isinstance(v, bool)

        return value if numeric(longitude) and numeric(latitude) else None
    return value


class Location(BaseModel):
    """经纬度。前端用它在地图上打点（Result.vue:825 判真值后使用）。"""

    longitude: float = Field(..., description="经度")
    latitude: float = Field(..., description="纬度")


class Attraction(BaseModel):
    name: str = Field(..., description="景点名称")
    address: str = Field(..., description="地址")
    # 允许为空：模型可能拿不到坐标；能补的由 orchestrator 用 maps_geo 补齐
    location: Optional[Location] = Field(default=None, description="经纬度坐标")

    @field_validator("location", mode="before")
    @classmethod
    def drop_incomplete_location(cls, value):
        return _coerce_incomplete_location(value)

    visit_duration: int = Field(..., description="建议游览时间(分钟)")
    description: str = Field(..., description="景点描述")
    category: Optional[str] = Field(default="景点", description="景点类别")
    rating: Optional[float] = Field(default=None, description="评分")
    photos: List[str] = Field(default_factory=list, description="图片URL列表（前端不读，透传）")
    poi_id: Optional[str] = Field(default="", description="POI ID（前端不读，透传）")
    image_url: Optional[str] = Field(default=None, description="图片URL（前端不读，透传）")
    ticket_price: int = Field(default=0, description="门票价格(元)")


class Meal(BaseModel):
    type: str = Field(..., description="餐饮类型: breakfast/lunch/dinner/snack")
    name: str = Field(..., description="餐饮名称")
    address: Optional[str] = Field(default=None, description="地址")
    location: Optional[Location] = Field(default=None, description="经纬度坐标")
    description: Optional[str] = Field(default=None, description="描述")
    estimated_cost: int = Field(default=0, description="预估费用(元)")


class Hotel(BaseModel):
    name: str = Field(..., description="酒店名称")
    address: str = Field(default="", description="酒店地址")
    # 同 Attraction.location：允许为空，能补的用 maps_geo 补
    location: Optional[Location] = Field(default=None, description="酒店位置")

    @field_validator("location", mode="before")
    @classmethod
    def drop_incomplete_location(cls, value):
        return _coerce_incomplete_location(value)

    price_range: str = Field(default="", description="价格范围")
    # 注意：rating 是**字符串**语义 —— 前端渲染成 {{ hotel.rating }}⭐，
    # LLM 提示词里的示例也是 "4.5"。别改成数值类型，否则契约漂移。
    rating: str = Field(default="", description="评分")
    distance: str = Field(default="", description="距离景点距离")
    type: str = Field(default="", description="酒店类型")
    estimated_cost: int = Field(default=0, description="预估费用(元/晚)")


class DayPlan(BaseModel):
    date: str = Field(..., description="日期 YYYY-MM-DD")
    day_index: int = Field(..., description="第几天（**从 0 开始**，前端用 day_index+1 显示）")
    description: str = Field(..., description="当日行程描述")
    transportation: str = Field(..., description="交通方式")
    accommodation: str = Field(..., description="住宿")
    hotel: Optional[Hotel] = Field(default=None, description="推荐酒店")
    attractions: List[Attraction] = Field(default_factory=list, description="景点列表")
    meals: List[Meal] = Field(default_factory=list, description="餐饮列表")


class WeatherInfo(BaseModel):
    date: str = Field(..., description="日期 YYYY-MM-DD")
    day_weather: str = Field(default="", description="白天天气")
    night_weather: str = Field(default="", description="夜间天气")
    day_temp: Union[int, str] = Field(default=0, description="白天温度")
    night_temp: Union[int, str] = Field(default=0, description="夜间温度")
    wind_direction: str = Field(default="", description="风向")
    wind_power: str = Field(default="", description="风力")

    @field_validator("day_temp", "night_temp", mode="before")
    @classmethod
    def parse_temperature(cls, value):
        """把 '25°C' / '25℃' / '25' 归一化成 int。

        离开本服务必须是纯数字：前端会自己补单位，带单位会渲染成 "25°C°C"，契约闸门也会判红。
        """

        if isinstance(value, str):
            cleaned = value.replace("°C", "").replace("℃", "").replace("°", "").strip()
            try:
                return int(float(cleaned))
            except ValueError:
                return 0
        return value


class Budget(BaseModel):
    total_attractions: int = Field(default=0, description="景点门票总费用")
    total_hotels: int = Field(default=0, description="酒店总费用")
    total_meals: int = Field(default=0, description="餐饮总费用")
    total_transportation: int = Field(default=0, description="交通总费用")
    total: int = Field(default=0, description="总费用")


class TripPlan(BaseModel):
    """Agent 返回给 BFF 的**裸**行程对象（没有 success/message 外壳）。"""

    city: str = Field(..., description="目的地城市")
    start_date: str = Field(..., description="开始日期")
    end_date: str = Field(..., description="结束日期")
    days: List[DayPlan] = Field(..., description="每日行程（绝不能为 null）")
    weather_info: List[WeatherInfo] = Field(default_factory=list, description="天气信息")
    overall_suggestions: str = Field(..., description="总体建议")
    budget: Optional[Budget] = Field(default=None, description="预算信息")
