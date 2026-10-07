package com.helloagents.travel.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * 图片接口外壳。
 *
 * <p>注意：该接口即使上游失败也返回 HTTP 200 + success=true + photo_url=null
 * （前端 Result.vue:438 只判 success 与 photo_url，失败仅 console.error），
 * 绝不能返回 5xx —— 那会在结果页产生一堆错误提示。
 */
public record PhotoResponseDto(

        @JsonProperty("success")
        Boolean success,

        @JsonProperty("message")
        String message,

        @JsonProperty("data")
        PhotoDataDto data) {
}
