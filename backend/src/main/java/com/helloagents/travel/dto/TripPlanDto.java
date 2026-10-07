package com.helloagents.travel.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/**
 * 行程本体（前端 {@code TripPlan}，types/index.ts:69）。
 *
 * <p>可空性红线（附录 A）：
 * <ul>
 *   <li>{@code days} —— <b>绝不能为 null</b>：Result.vue:433/824 直接对它 .forEach，会抛 TypeError</li>
 *   <li>{@code weather_info} —— 可为 null（模板有 v-if），但正常都给数组</li>
 *   <li>{@code budget} —— 可为 null（模板 46/85 有 v-if）</li>
 *   <li>{@code overall_suggestions} —— 模板未判空，必须给字符串</li>
 * </ul>
 */
public record TripPlanDto(

        @JsonProperty("city")
        String city,

        @JsonProperty("start_date")
        String startDate,

        @JsonProperty("end_date")
        String endDate,

        @JsonProperty("days")
        List<DayPlanDto> days,

        @JsonProperty("weather_info")
        List<WeatherInfoDto> weatherInfo,

        @JsonProperty("overall_suggestions")
        String overallSuggestions,

        @JsonProperty("budget")
        BudgetDto budget) {
}
