package com.helloagents.travel.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * 餐饮（前端 {@code Meal}，types/index.ts:20）。
 *
 * <p>{@code type} 取值必须是 breakfast/lunch/dinner/snack，
 * 前端 {@code getMealLabel(meal.type)} 依赖它做中文展示。
 */
public record MealDto(

        @JsonProperty("type")
        String type,

        @JsonProperty("name")
        String name,

        @JsonProperty("address")
        String address,

        @JsonProperty("location")
        LocationDto location,

        @JsonProperty("description")
        String description,

        @JsonProperty("estimated_cost")
        Integer estimatedCost) {
}
