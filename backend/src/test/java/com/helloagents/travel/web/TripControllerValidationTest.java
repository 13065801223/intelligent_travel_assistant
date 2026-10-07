package com.helloagents.travel.web;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.helloagents.travel.dto.BudgetDto;
import com.helloagents.travel.dto.DayPlanDto;
import com.helloagents.travel.dto.TripPlanDto;
import com.helloagents.travel.dto.TripPlanResponseDto;
import com.helloagents.travel.service.TripPlanService;
import com.helloagents.travel.support.ApiException;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

/**
 * Web 层切片测试：守护"校验失败必须是 400 且错误体含 detail 字符串"这条前端红线。
 *
 * <p>为什么这条最重要：前端 api.ts:47 是
 * {@code throw new Error(error.response?.data?.detail || error.message)}。
 * 如果 detail 缺失（例如被 RFC7807 顶掉、或变成数组），用户只会看到
 * {@code Request failed with status code 400} 这种无用文案。
 */
@WebMvcTest(controllers = TripController.class)
class TripControllerValidationTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private TripPlanService tripPlanService;

    @Test
    @DisplayName("travel_days=0 → 400，且错误体含字符串 detail")
    void travelDaysZeroReturns400WithDetail() throws Exception {
        String body = """
                {
                  "city": "杭州",
                  "start_date": "2026-10-10",
                  "end_date": "2026-10-10",
                  "travel_days": 0,
                  "transportation": "公共交通",
                  "accommodation": "经济型酒店",
                  "preferences": [],
                  "free_text_input": ""
                }
                """;

        mockMvc.perform(post("/api/trip/plan")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").isString())
                .andExpect(jsonPath("$.detail").isNotEmpty())
                .andExpect(jsonPath("$.message").isString())
                .andExpect(jsonPath("$.success").value(false))
                .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.traceId").isString());
    }

    @Test
    @DisplayName("缺 city → 400，detail 里点名缺失字段")
    void missingCityReturns400() throws Exception {
        String body = """
                {
                  "start_date": "2026-10-10",
                  "end_date": "2026-10-10",
                  "travel_days": 1,
                  "transportation": "公共交通",
                  "accommodation": "经济型酒店"
                }
                """;

        mockMvc.perform(post("/api/trip/plan")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").isString())
                .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
    }

    @Test
    @DisplayName("非 YYYY-MM-DD 日期 → 400")
    void badDateFormatReturns400() throws Exception {
        String body = """
                {
                  "city": "杭州",
                  "start_date": "2026/10/10",
                  "end_date": "2026-10-10",
                  "travel_days": 1,
                  "transportation": "公共交通",
                  "accommodation": "经济型酒店"
                }
                """;

        mockMvc.perform(post("/api/trip/plan")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
    }

    @Test
    @DisplayName("合法请求 → 200 且字段名是 snake_case（契约不能被命名策略改掉）")
    void validRequestReturnsSnakeCaseEnvelope() throws Exception {
        given(tripPlanService.plan(any())).willReturn(sampleResponse());

        String body = """
                {
                  "city": "杭州",
                  "start_date": "2026-10-10",
                  "end_date": "2026-10-10",
                  "travel_days": 1,
                  "transportation": "公共交通",
                  "accommodation": "经济型酒店",
                  "preferences": ["自然风光"],
                  "free_text_input": ""
                }
                """;

        mockMvc.perform(post("/api/trip/plan")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.message").value("旅行计划生成成功"))
                .andExpect(jsonPath("$.data.city").value("杭州"))
                .andExpect(jsonPath("$.data.start_date").value("2026-10-10"))
                .andExpect(jsonPath("$.data.days[0].day_index").value(0))
                .andExpect(jsonPath("$.data.days[0].attractions").isArray())
                .andExpect(jsonPath("$.data.days[0].meals").isArray())
                .andExpect(jsonPath("$.data.budget.total_hotels").value(480));
    }

    @Test
    @DisplayName("Agent 读超时 → 504，detail 可读（不让用户看到浏览器裸超时）")
    void agentTimeoutMapsTo504WithReadableDetail() throws Exception {
        given(tripPlanService.plan(any()))
                .willThrow(new ApiException(504, "AGENT_TIMEOUT", "行程生成超时，请稍后重试（traceId: abc12345）"));

        mockMvc.perform(post("/api/trip/plan")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(minimalRequest()))
                .andExpect(status().isGatewayTimeout())
                .andExpect(jsonPath("$.code").value("AGENT_TIMEOUT"))
                .andExpect(jsonPath("$.detail").value("行程生成超时，请稍后重试（traceId: abc12345）"))
                .andExpect(jsonPath("$.success").value(false));
    }

    @Test
    @DisplayName("Agent 连不上 → 503")
    void agentUnavailableMapsTo503() throws Exception {
        given(tripPlanService.plan(any()))
                .willThrow(new ApiException(503, "AGENT_UNAVAILABLE", "行程服务暂时不可用，请稍后重试"));

        mockMvc.perform(post("/api/trip/plan")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(minimalRequest()))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.code").value("AGENT_UNAVAILABLE"))
                .andExpect(jsonPath("$.detail").isString());
    }

    // ---------------------------------------------------------------- 测试数据

    private static String minimalRequest() {
        return """
                {
                  "city": "杭州",
                  "start_date": "2026-10-10",
                  "end_date": "2026-10-10",
                  "travel_days": 1,
                  "transportation": "公共交通",
                  "accommodation": "经济型酒店"
                }
                """;
    }

    private static TripPlanResponseDto sampleResponse() {
        DayPlanDto day = new DayPlanDto(
                "2026-10-10", 0, "第1天：西湖", "公共交通", "经济型酒店",
                null, List.of(), List.of());
        TripPlanDto plan = new TripPlanDto(
                "杭州", "2026-10-10", "2026-10-10",
                List.of(day), List.of(), "建议提前查看开放时间",
                new BudgetDto(0, 480, 0, 0, 480));
        return new TripPlanResponseDto(true, "旅行计划生成成功", plan);
    }
}
