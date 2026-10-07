package com.helloagents.travel.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/**
 * 景点（前端 {@code Attraction}，types/index.ts:8）。
 *
 * <p>字段说明：
 * <ul>
 *   <li>{@code name} —— 模板渲染，同时是 {@code /api/poi/photo} 的查询关键字</li>
 *   <li>{@code location} —— Result.vue:825 判真值后用于地图打点，经纬度必须是数字</li>
 *   <li>{@code ticket_price} / {@code rating} —— 前端 v-if 判真值，0 与 null 都不显示，安全</li>
 *   <li>{@code category} —— 前端查看模式未渲染，仅透传</li>
 *   <li>{@code photos} / {@code poi_id} / {@code image_url} —— 前端不读，透传以保持契约等价</li>
 * </ul>
 */
public record AttractionDto(

        @JsonProperty("name")
        String name,

        @JsonProperty("address")
        String address,

        @JsonProperty("location")
        LocationDto location,

        @JsonProperty("visit_duration")
        Integer visitDuration,

        @JsonProperty("description")
        String description,

        @JsonProperty("category")
        String category,

        @JsonProperty("rating")
        Double rating,

        @JsonProperty("photos")
        List<String> photos,

        @JsonProperty("poi_id")
        String poiId,

        @JsonProperty("image_url")
        String imageUrl,

        @JsonProperty("ticket_price")
        Integer ticketPrice) {
}
