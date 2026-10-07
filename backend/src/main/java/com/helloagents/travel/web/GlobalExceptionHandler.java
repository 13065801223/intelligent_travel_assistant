package com.helloagents.travel.web;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.helloagents.travel.support.ApiException;
import com.helloagents.travel.support.TraceIdFilter;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.client.ResourceAccessException;

/**
 * 全局错误翻译：所有异常都变成"含 detail 字符串"的统一错误体。
 *
 * <p><b>为什么必须有 detail</b>：前端 api.ts:47 是
 * {@code throw new Error(error.response?.data?.detail || error.message)}，
 * 它只认 {@code detail}。没有这个字段，用户只能看到
 * {@code Request failed with status code 500}，等于没有错误信息。
 *
 * <p>状态码映射（见 docs §2.3）：
 * <ul>
 *   <li>400 VALIDATION_FAILED —— Bean Validation 失败 / 请求体不是合法 JSON</li>
 *   <li>503 AGENT_UNAVAILABLE —— Agent 连接被拒或连接超时</li>
 *   <li>504 AGENT_TIMEOUT —— Agent 读超时（由 AgentClient 判定后抛出）</li>
 *   <li>502 AGENT_BAD_RESPONSE —— Agent 返回 4xx/5xx 或返回体无法反序列化</li>
 *   <li>500 INTERNAL_ERROR —— 其它未预期异常</li>
 * </ul>
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    /**
     * 错误体（冻结）。
     *
     * <p>{@code detail} 与 {@code message} 给同一个可读串：前者满足前端，后者维持旧契约兼容；
     * {@code success=false} 让"把错误当成功解析"的客户端不可能误判。
     */
    public record ErrorResponse(

            @JsonProperty("detail")
            String detail,

            @JsonProperty("message")
            String message,

            @JsonProperty("success")
            boolean success,

            @JsonProperty("code")
            String code,

            @JsonProperty("traceId")
            String traceId) {
    }

    /** 受控异常：状态码与错误码都由抛出方决定（AgentClient 的三分类走这里）。 */
    @ExceptionHandler(ApiException.class)
    public ResponseEntity<ErrorResponse> handleApi(ApiException e) {
        log.warn("业务失败 code={} status={} detail={}", e.getCode(), e.getStatus(), e.getDetail());
        return ResponseEntity.status(e.getStatus()).body(error(e.getCode(), e.getDetail()));
    }

    /** @Valid 校验失败：把字段名与原因拼进 detail，便于用户/排障定位。 */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> handleValidation(MethodArgumentNotValidException e) {
        String detail = e.getBindingResult().getFieldErrors().stream()
                .map(fieldError -> fieldError.getField() + ": " + fieldError.getDefaultMessage())
                .collect(Collectors.joining("; "));
        if (detail.isBlank()) {
            detail = "请求参数校验失败";
        }
        log.warn("参数校验失败 detail={}", detail);
        return ResponseEntity.badRequest().body(error("VALIDATION_FAILED", detail));
    }

    /** 请求体不是合法 JSON（或字段类型完全无法转换）。 */
    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ErrorResponse> handleUnreadable(HttpMessageNotReadableException e) {
        log.warn("请求体无法解析: {}", e.getMessage());
        return ResponseEntity.badRequest().body(error("VALIDATION_FAILED", "请求体不是合法 JSON"));
    }

    /**
     * 兜底：理论上 AgentClient 已经把 ResourceAccessException 分类过了，
     * 这里只防漏网（例如将来别处新增了出网调用）。
     */
    @ExceptionHandler(ResourceAccessException.class)
    public ResponseEntity<ErrorResponse> handleResourceAccess(ResourceAccessException e) {
        log.warn("上游不可达: {}", e.toString());
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(error("AGENT_UNAVAILABLE", "上游服务暂时不可用，请稍后重试"));
    }

    /** 未预期异常：日志留全栈，响应只给通用文案 + traceId。 */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleUnexpected(Exception e) {
        log.error("未预期异常", e);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(error("INTERNAL_ERROR", "服务器内部错误，请稍后重试"));
    }

    private static ErrorResponse error(String code, String detail) {
        return new ErrorResponse(detail, detail, false, code, TraceIdFilter.currentTraceId());
    }
}
