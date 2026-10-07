package com.helloagents.travel.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * 图片数据。{@code photo_url} 为 null 表示"没找到/上游失败"，
 * 前端会退化成内置的渐变占位图（Result.vue:490）。
 */
public record PhotoDataDto(

        @JsonProperty("name")
        String name,

        @JsonProperty("photo_url")
        String photoUrl) {
}
