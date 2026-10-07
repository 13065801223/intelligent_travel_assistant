package com.helloagents.travel.config;

import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * BFF 自身配置（{@code app.*}）。
 *
 * <p>注意这里【没有】高德 API Key：高德数据全部由 Python Agent 侧的 MCP 工具获取，
 * BFF 只需要 Agent 地址与 Unsplash 凭据。地图 JS API Key 属于前端，与本进程无关。
 *
 * @param agent    Python Agent 服务（内网）
 * @param unsplash 景点图片（确定性 REST，失败不影响主流程）
 * @param cors     跨域放行来源
 */
@ConfigurationProperties(prefix = "app")
public record AppProperties(Agent agent, Unsplash unsplash, Cors cors) {

    /**
     * @param baseUrl        Agent 服务地址，默认 127.0.0.1:8100（只监听内网）
     * @param planPath       生成行程的内部路径，返回裸 TripPlan
     * @param healthPath     健康探测路径，需暴露 mcp.tools 数量
     * @param connectTimeout 连接超时：连不上要快速失败，不能吃掉生成预算
     * @param readTimeout    读超时：必须严格小于前端 axios 的超时（内层 < 外层）
     */
    public record Agent(
            String baseUrl,
            String planPath,
            String healthPath,
            Duration connectTimeout,
            Duration readTimeout) {
    }

    /**
     * @param baseUrl       Unsplash API 根地址
     * @param accessKey     仅需 access key（旧项目里的 secret 从未被使用，故不迁移）
     * @param connectTimeout 连接超时
     * @param readTimeout    读超时，保持很短：图片是增强项
     */
    public record Unsplash(
            String baseUrl,
            String accessKey,
            Duration connectTimeout,
            Duration readTimeout) {
    }

    /**
     * @param allowedOrigins 放行来源；前端页面可能在 localhost/127.0.0.1 的 5173/3000 上打开
     */
    public record Cors(List<String> allowedOrigins) {
    }
}
