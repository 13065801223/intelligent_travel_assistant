package com.helloagents.travel.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * 酒店（前端 {@code Hotel}，types/index.ts:29）。
 *
 * <p><b>注意 {@code rating} 是 String 而不是数字</b>：Result.vue:236 渲染为 {@code {{ hotel.rating }}⭐}，
 * 旧契约与 LLM 提示词示例给的都是 {@code "4.5"}。改成数值会与 Python 侧 Pydantic 模型
 * （{@code rating: str}）不一致，触发契约漂移。
 */
public record HotelDto(

        @JsonProperty("name")
        String name,

        @JsonProperty("address")
        String address,

        @JsonProperty("location")
        LocationDto location,

        @JsonProperty("price_range")
        String priceRange,

        @JsonProperty("rating")
        String rating,

        @JsonProperty("distance")
        String distance,

        @JsonProperty("type")
        String type,

        @JsonProperty("estimated_cost")
        Integer estimatedCost) {
}
