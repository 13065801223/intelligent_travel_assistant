package com.helloagents.travel.client;

import com.fasterxml.jackson.databind.JsonNode;
import com.helloagents.travel.config.AppProperties;
import com.helloagents.travel.config.HttpClientConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/**
 * Unsplash 图片搜索（确定性 REST，放 BFF 侧）。
 *
 * <p>契约行为复刻旧实现 {@code unsplash_service.get_photo_url}：
 * {@code GET /search/photos?query=..&per_page=1&client_id=..}，取 {@code results[0].urls.regular}。
 *
 * <p><b>本类永不抛异常</b>：任何失败（无 key、超时、4xx/5xx、结构变化）一律返回 null。
 * 调用方据此给出 {@code photo_url=null}，前端退化成占位图 —— 图片只是增强项，
 * 绝不能因为第三方挂掉而让结果页报错。
 */
@Component
public class UnsplashClient {

    private static final Logger log = LoggerFactory.getLogger(UnsplashClient.class);

    private final RestClient restClient;
    private final AppProperties props;

    public UnsplashClient(@Qualifier(HttpClientConfig.UNSPLASH_REST_CLIENT) RestClient unsplashRestClient,
                          AppProperties props) {
        this.restClient = unsplashRestClient;
        this.props = props;
    }

    /**
     * @return 图片 URL；找不到或任何异常都返回 {@code null}
     */
    public String firstPhotoUrl(String query) {
        String accessKey = props.unsplash().accessKey();
        if (accessKey == null || accessKey.isBlank()) {
            log.debug("未配置 UNSPLASH_ACCESS_KEY，跳过图片查询 query={}", query);
            return null;
        }
        if (query == null || query.isBlank()) {
            return null;
        }
        try {
            JsonNode body = restClient.get()
                    .uri(uriBuilder -> uriBuilder
                            .path("/search/photos")
                            .queryParam("query", query)
                            .queryParam("per_page", 1)
                            .queryParam("client_id", accessKey)
                            .build())
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .body(JsonNode.class);

            if (body == null) {
                return null;
            }
            JsonNode first = body.path("results").path(0);
            String url = first.path("urls").path("regular").asText(null);
            return (url == null || url.isBlank()) ? null : url;

        } catch (Exception e) {
            log.warn("Unsplash 查询失败（已降级为占位图）query={} error={}", query, e.toString());
            return null;
        }
    }
}
