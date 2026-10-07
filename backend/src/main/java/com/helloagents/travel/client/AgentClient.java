package com.helloagents.travel.client;

import com.helloagents.travel.config.AppProperties;
import com.helloagents.travel.config.HttpClientConfig;
import com.helloagents.travel.dto.TripPlanDto;
import com.helloagents.travel.dto.TripRequestDto;
import com.helloagents.travel.support.ApiException;
import com.helloagents.travel.support.TraceIdFilter;
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

/**
 * 调用 Python Agent 服务（内网 127.0.0.1:8100）。
 *
 * <p>内部契约：{@code POST /internal/v1/trip-plan} 请求体与公开请求体同构（snake_case），
 * 成功返回 <b>裸 TripPlan</b>（没有 {success,message,data} 外壳 —— 外壳归 BFF 所有）。
 *
 * <p>异常分类是本类存在的核心价值（见 docs §2.3 错误表）：
 * <ul>
 *   <li>连接被拒 / 连接超时 → 503 AGENT_UNAVAILABLE</li>
 *   <li>读超时 → 504 AGENT_TIMEOUT</li>
 *   <li>Agent 返回 4xx/5xx、或返回体无法反序列化 → 502 AGENT_BAD_RESPONSE</li>
 * </ul>
 * 连接超时与读超时在 Spring 里都是 {@link ResourceAccessException}，必须看 cause 才能区分，
 * 否则用户分不清"服务没起来"和"生成太慢"。
 */
@Component
public class AgentClient {

    private static final Logger log = LoggerFactory.getLogger(AgentClient.class);

    private final RestClient restClient;
    private final AppProperties props;

    public AgentClient(@Qualifier(HttpClientConfig.AGENT_REST_CLIENT) RestClient agentRestClient,
                       AppProperties props) {
        this.restClient = agentRestClient;
        this.props = props;
    }

    /**
     * 请求 Agent 生成行程。
     *
     * @throws ApiException 503/504/502，含用户可读的中文 detail
     */
    public TripPlanDto plan(TripRequestDto request) {
        String traceId = TraceIdFilter.currentTraceId();
        long started = System.currentTimeMillis();
        try {
            TripPlanDto plan = restClient.post()
                    .uri(props.agent().planPath())
                    .header(TraceIdFilter.HEADER, traceId)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(request)
                    .retrieve()
                    .body(TripPlanDto.class);

            if (plan == null) {
                throw new ApiException(502, "AGENT_BAD_RESPONSE", "行程服务返回了空响应，请稍后重试");
            }
            requireStructurallyUsable(plan, traceId);
            log.info("agent plan ok traceId={} costMs={} days={}",
                    traceId, System.currentTimeMillis() - started,
                    plan.days() == null ? 0 : plan.days().size());
            return plan;

        } catch (ApiException e) {
            throw e;
        } catch (ResourceAccessException e) {
            Failure failure = classify(e);
            log.warn("agent unreachable traceId={} kind={} costMs={} cause={}",
                    traceId, failure, System.currentTimeMillis() - started,
                    e.getMostSpecificCause().getClass().getName());
            if (failure == Failure.READ_TIMEOUT) {
                throw new ApiException(504, "AGENT_TIMEOUT",
                        "行程生成超时，请稍后重试（traceId: " + traceId + "）", e);
            }
            throw new ApiException(503, "AGENT_UNAVAILABLE",
                    "行程服务暂时不可用，请稍后重试（traceId: " + traceId + "）", e);
        } catch (RestClientResponseException e) {
            // Agent 明确返回了 4xx/5xx：把它的状态码记进日志，但不要把内部细节透给用户
            log.warn("agent bad status traceId={} status={} body={}",
                    traceId, e.getStatusCode(), abbreviate(e.getResponseBodyAsString()));
            throw new ApiException(502, "AGENT_BAD_RESPONSE",
                    "行程生成失败，请稍后重试（traceId: " + traceId + "）", e);
        } catch (RestClientException e) {
            // 覆盖反序列化失败（例如温度带单位 "25°C" 塞进 Integer）等情况
            log.warn("agent bad payload traceId={} error={}", traceId, e.toString());
            throw new ApiException(502, "AGENT_BAD_RESPONSE",
                    "行程服务返回了无法解析的数据（traceId: " + traceId + "）", e);
        }
    }

    private enum Failure { CONNECT, READ_TIMEOUT, OTHER }
    /**
     * 区分连接类失败与读超时。
     *
     * <p>注意 JDK HttpClient 的两种超时是两个类：
     * 连接超时 = {@code HttpConnectTimeoutException}，读超时 = {@code HttpTimeoutException}
     * （前者是后者的子类，所以必须先判连接）。另外为兼容其它 requestFactory，
     * 同时识别 {@link SocketTimeoutException}（Spring 文档里常见的读超时 cause）。
     */
    /**
     * 结构红线守卫：Agent 返回 HTTP 200 **并不代表**返回的数据能用。
     *
     * <p>为什么需要它（真实踩过）：Agent 若返回了一个结构不对但仍是合法 JSON 的对象
     * （例如 {@code {"probe":true}}），Jackson 会把未知字段忽略、其余字段全留 null，
     * 于是 BFF 高高兴兴地 200 返回 {@code days: null} —— 前端 Result.vue:433/824
     * 对 {@code days} 及其下 {@code attractions} 直接 {@code .forEach} 且无判空，
     * 结果就是 "Cannot read properties of undefined"。
     *
     * <p>只守"前端会直接崩"的那几个字段。完整字段级契约由 {@code tools/check_contract.py}
     * 在测试期把关；这里**不复制** Python 的清洗规则（否则会出现第二个 Owner）。
     */
    public static void requireStructurallyUsable(TripPlanDto plan, String traceId) {
        boolean broken = plan.days() == null
                || plan.days().isEmpty()
                || plan.days().stream()
                        .anyMatch(day -> day == null || day.attractions() == null || day.meals() == null);
        if (broken) {
            log.warn("agent plan structurally unusable traceId={} days={}", traceId,
                    plan.days() == null ? "null" : String.valueOf(plan.days().size()));
            throw new ApiException(502, "AGENT_BAD_RESPONSE",
                    "行程服务返回的数据不完整，请稍后重试（traceId: " + traceId + "）");
        }
    }

    private static Failure classify(Throwable error) {
        boolean sawTimeout = false;
        for (Throwable cause = error; cause != null; cause = cause.getCause()) {
            String name = cause.getClass().getName();
            if (name.equals("java.net.http.HttpConnectTimeoutException") || cause instanceof ConnectException) {
                return Failure.CONNECT;
            }
            if (cause instanceof SocketTimeoutException) {
                sawTimeout = true;
            }
            if (name.equals("java.net.http.HttpTimeoutException")) {
                sawTimeout = true;
            }
        }
        return sawTimeout ? Failure.READ_TIMEOUT : Failure.OTHER;
    }

    private static String abbreviate(String text) {
        if (text == null) {
            return "";
        }
        return text.length() <= 300 ? text : text.substring(0, 300) + "...";
    }
}
