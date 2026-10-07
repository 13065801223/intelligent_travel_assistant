package com.helloagents.travel.support;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * 给每次请求分配/透传一个 traceId，用于把 BFF 与 Agent 两端日志串起来。
 *
 * <p>链路：前端 → BFF（本过滤器生成或透传入站 X-Trace-Id）→ 带上同名头调用 Agent
 * → Agent 回写同一 id → 出错时错误体里也带它。用户报障时只要一个 traceId 就能两端对齐。
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class TraceIdFilter extends OncePerRequestFilter {

    /** 请求/响应头名，同时也是调用 Agent 时透传的头名。 */
    public static final String HEADER = "X-Trace-Id";

    /** 日志 MDC 键名，与 application.yml 的 logging pattern {@code %X{traceId:-}} 对应。 */
    public static final String MDC_KEY = "traceId";

    /** 供 Service/Client 读取当前请求的 traceId（MDC 是 ThreadLocal，同一线程内可见）。 */
    public static String currentTraceId() {
        String traceId = MDC.get(MDC_KEY);
        return (traceId == null || traceId.isBlank()) ? "unknown" : traceId;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String traceId = request.getHeader(HEADER);
        if (traceId == null || traceId.isBlank()) {
            traceId = UUID.randomUUID().toString().replace("-", "").substring(0, 8);
        }
        MDC.put(MDC_KEY, traceId);
        response.setHeader(HEADER, traceId);
        try {
            filterChain.doFilter(request, response);
        } finally {
            // 必须清理：Tomcat 线程会被复用，残留 MDC 会污染下一个请求的日志
            MDC.remove(MDC_KEY);
        }
    }
}
