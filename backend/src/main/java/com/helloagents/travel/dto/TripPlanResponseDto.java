package com.helloagents.travel.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * 响应外壳（前端 {@code TripPlanResponse}，types/index.ts:90）。
 *
 * <p>这三个字段是前端判断成败的全部依据：
 * <ul>
 *   <li>{@code success} —— Home.vue:297 判断是否跳转结果页</li>
 *   <li>{@code message} —— Home.vue:308 在 success=false 时展示</li>
 *   <li>{@code data} —— 行程本体，可为 null</li>
 * </ul>
 * 外壳由 BFF 拥有；Python Agent 的内部接口返回的是**裸 TripPlan**（无外壳）。
 */
public record TripPlanResponseDto(

        @JsonProperty("success")
        Boolean success,

        @JsonProperty("message")
        String message,

        @JsonProperty("data")
        TripPlanDto data) {
}
