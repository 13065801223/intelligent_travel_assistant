package com.helloagents.travel;

import com.helloagents.travel.config.AppProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

/**
 * 智能旅行助手 BFF（对外唯一入口）。
 *
 * <p>职责边界（见 docs/backend-dev-guide.md §2.2）：
 * <ul>
 *   <li>对外 HTTP 契约、请求校验、CORS、统一错误体、超时分层 —— 本进程拥有</li>
 *   <li>LLM / MCP / 高德数据 —— 归 Python Agent 服务（默认 127.0.0.1:8100）</li>
 *   <li>Unsplash 图片 —— 确定性 REST，放本进程</li>
 *   <li>地图 JS API —— 前端自己加载，与本进程无关</li>
 * </ul>
 *
 * <p>{@code @EnableConfigurationProperties} 显式注册 AppProperties：切片测试
 * （@WebMvcTest）也会以本类为配置源，显式注册比依赖扫描更稳。
 */
@SpringBootApplication
@EnableConfigurationProperties(AppProperties.class)
public class TravelApplication {

    public static void main(String[] args) {
        SpringApplication.run(TravelApplication.class, args);
    }
}
