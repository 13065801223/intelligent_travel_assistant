package com.helloagents.travel.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/**
 * 单日行程（前端 {@code DayPlan}，types/index.ts:48）。
 *
 * <p>可空性红线：
 * <ul>
 *   <li>{@code attractions} / {@code meals} —— <b>绝不能为 null</b>：Result.vue:434/824 与 245
 *       直接 .forEach / v-for，null 会抛 TypeError</li>
 *   <li>{@code hotel} —— 可为 null（模板 227/228 有 v-if）</li>
 *   <li>{@code day_index} —— <b>从 0 开始</b>：Result.vue:54 用 day_index + 1 显示"第 N 天"</li>
 * </ul>
 */
public record DayPlanDto(

        @JsonProperty("date")
        String date,

        @JsonProperty("day_index")
        Integer dayIndex,

        @JsonProperty("description")
        String description,

        @JsonProperty("transportation")
        String transportation,

        @JsonProperty("accommodation")
        String accommodation,

        @JsonProperty("hotel")
        HotelDto hotel,

        @JsonProperty("attractions")
        List<AttractionDto> attractions,

        @JsonProperty("meals")
        List<MealDto> meals) {
}
