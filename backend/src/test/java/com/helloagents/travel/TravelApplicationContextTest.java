package com.helloagents.travel;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

/**
 * 启动冒烟：证明整个应用上下文能装配起来。
 *
 * <p>它守的是切片测试（@WebMvcTest）看不到的东西：
 * {@code AppProperties} 的 YAML 绑定、两个 RestClient Bean（@Qualifier 注入）、
 * CORS 配置、HealthIndicator 是否都能创建。这些一旦坏掉，只有真正启动时才会炸。
 *
 * <p>注意：本测试不起真实端口（webEnvironment 默认 MOCK），也不发起任何出网调用。
 */
@SpringBootTest
class TravelApplicationContextTest {

    @Test
    void contextLoads() {
    }
}
