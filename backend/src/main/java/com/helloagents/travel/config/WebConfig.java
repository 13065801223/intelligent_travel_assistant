package com.helloagents.travel.config;

import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * CORS：前端跑在 5173，BFF 在 8000，两个接口都是跨域请求。
 *
 * <p>其中 {@code GET /api/poi/photo} 前端用的是**裸 fetch()**（不带 cookie），
 * 所以这里刻意 **不配置** {@code allowCredentials(true)}：它与通配来源组合时 Spring 会直接报错，
 * 而本项目也根本不需要携带凭据。
 */
@Configuration
public class WebConfig implements WebMvcConfigurer {

    private final AppProperties props;

    public WebConfig(AppProperties props) {
        this.props = props;
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        List<String> origins = (props.cors() != null && props.cors().allowedOrigins() != null)
                ? props.cors().allowedOrigins()
                : List.of();
        registry.addMapping("/api/**")
                .allowedOrigins(origins.toArray(String[]::new))
                .allowedMethods("GET", "POST", "OPTIONS")
                .allowedHeaders("*");
    }
}
