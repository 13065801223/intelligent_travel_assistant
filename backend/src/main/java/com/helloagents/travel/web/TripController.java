package com.helloagents.travel.web;

import com.helloagents.travel.dto.TripPlanResponseDto;
import com.helloagents.travel.dto.TripRequestDto;
import com.helloagents.travel.service.TripPlanService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 主接口：{@code POST /api/trip/plan}（前端 api.ts:43 唯一调用的生成接口）。
 *
 * <p>契约（冻结）：请求体 = TripFormData；成功响应 = {@code {success,message,data}}；
 * 失败响应 = 全局错误体（含 detail 字符串）。
 */
@RestController
@RequestMapping("/api/trip")
public class TripController {

    private final TripPlanService tripPlanService;

    public TripController(TripPlanService tripPlanService) {
        this.tripPlanService = tripPlanService;
    }

    @PostMapping("/plan")
    public TripPlanResponseDto plan(@Valid @RequestBody TripRequestDto request) {
        // @Valid 失败会抛 MethodArgumentNotValidException，由 GlobalExceptionHandler 统一翻译成 400 + detail
        return tripPlanService.plan(request);
    }
}
