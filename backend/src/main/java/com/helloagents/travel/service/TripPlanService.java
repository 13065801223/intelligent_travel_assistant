package com.helloagents.travel.service;

import com.helloagents.travel.client.AgentClient;
import com.helloagents.travel.dto.TripPlanDto;
import com.helloagents.travel.dto.TripPlanResponseDto;
import com.helloagents.travel.dto.TripRequestDto;
import org.springframework.stereotype.Service;

/**
 * 行程编排：调 Agent → 包装公开外壳。
 *
 * <p>BFF 存在的意义之一就是"外壳归我"：Agent 只产出裸 {@link TripPlanDto}，
 * 由本类决定 message 文案与 success 语义（失败一律走 ApiException + 全局错误体，
 * <b>不再像旧实现那样返回编造的假行程</b>）。
 */
@Service
public class TripPlanService {

    private final AgentClient agentClient;

    public TripPlanService(AgentClient agentClient) {
        this.agentClient = agentClient;
    }

    public TripPlanResponseDto plan(TripRequestDto request) {
        TripPlanDto plan = agentClient.plan(request);
        return new TripPlanResponseDto(true, "旅行计划生成成功", plan);
    }
}
