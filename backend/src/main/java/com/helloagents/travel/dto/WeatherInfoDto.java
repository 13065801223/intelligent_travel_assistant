package com.helloagents.travel.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * 天气（前端 {@code WeatherInfo}，types/index.ts:59）。
 *
 * <p>可空性红线：{@code day_temp} / {@code night_temp} 必须是 <b>Integer</b>。
 * Result.vue:270/277 自己拼单位（{@code {{ item.day_temp }}°C}），
 * Agent 若返回 {@code "25°C"} 会显示成 {@code 25°C°C}。
 * 归一化（去掉 °C）由 Python 侧 Pydantic 负责；BFF 只做宽容反序列化，
 * 遇到带单位的字符串直接判为 502（AGENT_BAD_RESPONSE），不复制清洗规则。
 */
public record WeatherInfoDto(

        @JsonProperty("date")
        String date,

        @JsonProperty("day_weather")
        String dayWeather,

        @JsonProperty("night_weather")
        String nightWeather,

        @JsonProperty("day_temp")
        Integer dayTemp,

        @JsonProperty("night_temp")
        Integer nightTemp,

        @JsonProperty("wind_direction")
        String windDirection,

        @JsonProperty("wind_power")
        String windPower) {
}
