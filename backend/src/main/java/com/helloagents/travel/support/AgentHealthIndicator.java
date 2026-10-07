package com.helloagents.travel.support;

import com.fasterxml.jackson.databind.JsonNode;
import com.helloagents.travel.config.AppProperties;
import com.helloagents.travel.config.HttpClientConfig;
import java.time.Duration;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/**
 * 把 Agent 服务（以及它的 MCP 工具发现结果）并进 {@code /actuator/health}。
 *
 * <p>为什么单独建一个探测客户端：Agent 的业务读超时是 590s（要等分钟级生成），
 * 用它做健康探测会让 /actuator/health 也卡几分钟。这里固定 2s 超时。
 *
 * <p>为什么要暴露 {@code mcpTools}：历史事故中 MCP 工具发现失败是**静默**的
 * （依赖冲突 → 工具列表为空 → 模型收到"未找到工具"后开始编造行程），
 * 运维侧完全看不出来。把工具数暴露出来，这条链路才可观测。
 */
@Component
public class AgentHealthIndicator implements HealthIndicator {

    private static final Duration PROBE_TIMEOUT = Duration.ofSeconds(2);

    private final AppProperties props;
    private final RestClient probeClient;

    public AgentHealthIndicator(AppProperties props) {
        this.props = props;
        this.probeClient = RestClient.builder()
                .baseUrl(props.agent().baseUrl())
                .requestFactory(HttpClientConfig.requestFactory(PROBE_TIMEOUT, PROBE_TIMEOUT))
                .build();
    }

    @Override
    public Health health() {
        try {
            JsonNode body = probeClient.get()
                    .uri(props.agent().healthPath())
                    .retrieve()
                    .body(JsonNode.class);

            if (body == null) {
                return Health.unknown()
                        .withDetail("agentBaseUrl", props.agent().baseUrl())
                        .withDetail("error", "Agent 健康接口返回空响应")
                        .build();
            }

            int mcpTools = body.path("mcp").path("tools").asInt(-1);
            boolean ok = "ok".equalsIgnoreCase(body.path("status").asText());

            Health.Builder builder = ok ? Health.up() : Health.unknown();
            builder.withDetail("agentBaseUrl", props.agent().baseUrl())
                    .withDetail("agentStatus", body.path("status").asText())
                    .withDetail("mcpTools", mcpTools);

            if (mcpTools == 0) {
                builder.withDetail("warning", "MCP 工具数为 0：Agent 侧工具发现失败，模型会编造行程数据");
            }
            return builder.build();

        } catch (Exception e) {
            // 健康检查绝不抛异常：探活失败本身就是一条健康信息
            return Health.down()
                    .withDetail("agentBaseUrl", props.agent().baseUrl())
                    .withDetail("error", e.getClass().getSimpleName() + ": " + e.getMessage())
                    .build();
        }
    }
}
