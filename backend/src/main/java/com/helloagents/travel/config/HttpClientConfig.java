package com.helloagents.travel.config;

import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

/**
 * 两个独立的 RestClient：Agent 与 Unsplash。
 *
 * <p>两者超时相差近百倍（590s vs 8s）。共用一个会让图片请求
 * 也去等几分钟，把结果页拖死。
 *
 * <p>为什么用 {@link JdkClientHttpRequestFactory} 显式设置超时：{@code RestClient} 默认
 * 不设读超时（等价于永不超时），那样前端 600s 早断了、BFF 还在傻等，错误也无法归因。
 * 这里把连接/读超时都显式钉死，并与 AgentClient 里的异常分类（503/504）配套。
 */
@Configuration
public class HttpClientConfig {

    /** Agent 调用专用 RestClient 的 bean 名（注入时必须用 @Qualifier 指定，因为同类型有两个）。 */
    public static final String AGENT_REST_CLIENT = "agentRestClient";

    /** Unsplash 调用专用 RestClient 的 bean 名。 */
    public static final String UNSPLASH_REST_CLIENT = "unsplashRestClient";

    @Bean(AGENT_REST_CLIENT)
    RestClient agentRestClient(AppProperties props) {
        AppProperties.Agent agent = props.agent();
        return RestClient.builder()
                .baseUrl(agent.baseUrl())
                .requestFactory(requestFactory(agent.connectTimeout(), agent.readTimeout()))
                .build();
    }

    @Bean(UNSPLASH_REST_CLIENT)
    RestClient unsplashRestClient(AppProperties props) {
        AppProperties.Unsplash unsplash = props.unsplash();
        return RestClient.builder()
                .baseUrl(unsplash.baseUrl())
                .requestFactory(requestFactory(unsplash.connectTimeout(), unsplash.readTimeout()))
                .build();
    }

    /**
     * 用 JDK HttpClient 作为底层，分别设置连接超时与读超时。
     *
     * <p>注意：JDK HttpClient 的读超时抛的是 {@code HttpTimeoutException}，
     * 连接超时抛的是 {@code HttpConnectTimeoutException}（前者的子类）——
     * AgentClient 里据此区分 504 与 503。
     */
    public static JdkClientHttpRequestFactory requestFactory(Duration connectTimeout, Duration readTimeout) {
        HttpClient httpClient = HttpClient.newBuilder()
                .connectTimeout(connectTimeout)
                // 必须显式钉死 HTTP/1.1。JDK HttpClient 默认 Version.HTTP_2，对 http:// 会先发
                // h2c 升级（Upgrade: h2c + Transfer-Encoding: chunked）；Python 侧 uvicorn 不支持
                // h2c，实测结果是 **POST 的请求体整段丢失**：
                //   Agent 侧报 422 {"loc":["body"],"input":null}
                //   探针服务器抓到 BODY_LEN=0
                // 而 GET 因为没有请求体所以看起来完全正常 —— "只有 POST 坏"极难从日志归因。
                // 见 docs/backend-dev-guide.md 的联调故障对照表。
                .version(HttpClient.Version.HTTP_1_1)
                .build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(httpClient);
        factory.setReadTimeout(readTimeout);
        return factory;
    }
}
