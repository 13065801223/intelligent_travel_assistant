package com.helloagents.travel.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * 经纬度。用包装类型 {@link Double} 而非 {@code double}：
 * 缺失时应为 null 而不是静默变成 0.0（0,0 是几内亚湾，地图会把点打到非洲）。
 */
public record LocationDto(

        @JsonProperty("longitude")
        Double longitude,

        @JsonProperty("latitude")
        Double latitude) {
}
