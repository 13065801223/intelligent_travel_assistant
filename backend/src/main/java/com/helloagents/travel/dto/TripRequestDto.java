package com.helloagents.travel.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.List;

/**
 * 请求契约（前端 {@code TripFormData}，见 types/index.ts:79）。
 *
 * <p>校验约束逐条对齐 Python 侧 Pydantic（旧 schemas.py 的 TripRequest）：
 * city/transportation/accommodation 必填、travel_days 1..30、日期 YYYY-MM-DD。
 * 刻意【不新增】比原后端更严格的字段间校验（例如 end_date &gt;= start_date），
 * 以保持"契约等价"，避免把原本能通过的请求拒掉。
 *
 * <p>每个组件都显式写 {@code @JsonProperty} 的 snake_case：契约可见性优先于代码简洁，
 * 隐式命名策略是最容易悄悄改坏契约的地方。
 */
public record TripRequestDto(

        @JsonProperty("city")
        @NotBlank(message = "city 不能为空")
        @Size(max = 64, message = "city 长度不能超过 64")
        String city,

        @JsonProperty("start_date")
        @NotBlank(message = "start_date 不能为空")
        @Pattern(regexp = "\\d{4}-\\d{2}-\\d{2}", message = "start_date 必须是 YYYY-MM-DD")
        String startDate,

        @JsonProperty("end_date")
        @NotBlank(message = "end_date 不能为空")
        @Pattern(regexp = "\\d{4}-\\d{2}-\\d{2}", message = "end_date 必须是 YYYY-MM-DD")
        String endDate,

        @JsonProperty("travel_days")
        @NotNull(message = "travel_days 不能为空")
        @Min(value = 1, message = "travel_days 必须在 1..30")
        @Max(value = 30, message = "travel_days 必须在 1..30")
        Integer travelDays,

        @JsonProperty("transportation")
        @NotBlank(message = "transportation 不能为空")
        String transportation,

        @JsonProperty("accommodation")
        @NotBlank(message = "accommodation 不能为空")
        String accommodation,

        // 可选：Pydantic 侧默认 []；前端总是会发这个字段
        @JsonProperty("preferences")
        List<String> preferences,

        // 可选：Pydantic 侧默认 ""，且允许 null
        @JsonProperty("free_text_input")
        String freeTextInput) {
}
