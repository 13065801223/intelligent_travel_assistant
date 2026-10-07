package com.helloagents.travel.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * 预算（前端 {@code Budget}，types/index.ts:40）。
 *
 * <p>整个 budget 对象可为 null（模板 46/85 有 v-if）；一旦出现，
 * 五个字段前端都直接渲染 {@code ¥{{ }}}，缺字段会显示空值但不会崩。
 */
public record BudgetDto(

        @JsonProperty("total_attractions")
        Integer totalAttractions,

        @JsonProperty("total_hotels")
        Integer totalHotels,

        @JsonProperty("total_meals")
        Integer totalMeals,

        @JsonProperty("total_transportation")
        Integer totalTransportation,

        @JsonProperty("total")
        Integer total) {
}
