package com.helloagents.travel.support;

/**
 * 受控异常：把"哪里错了"与"对前端显示什么"分开。
 *
 * <p>{@code status} 决定 HTTP 状态码（给运维/curl 看），{@code code} 是稳定错误码（给日志与后续前端升级看），
 * {@code detail} 是给用户看的中文原因 —— 前端 api.ts:47 读的正是 {@code error.response.data.detail}。
 */
public class ApiException extends RuntimeException {

    private final int status;
    private final String code;

    public ApiException(int status, String code, String detail) {
        super(detail);
        this.status = status;
        this.code = code;
    }

    public ApiException(int status, String code, String detail, Throwable cause) {
        super(detail, cause);
        this.status = status;
        this.code = code;
    }

    public int getStatus() {
        return status;
    }

    public String getCode() {
        return code;
    }

    /** 与 {@link #getMessage()} 同义，单独命名以强调它会被放进响应体的 detail 字段。 */
    public String getDetail() {
        return getMessage();
    }
}
