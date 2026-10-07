package com.helloagents.travel;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.helloagents.travel.dto.TripPlanResponseDto;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Set;
import java.util.TreeSet;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * 契约测试（BFF 侧）：证明 DTO 与冻结契约逐字段一致。
 *
 * <p>它守护的是最容易悄悄坏掉的东西：字段名漂移、可空性漂移、类型漂移。
 * 与 Python 侧 {@code agent/tests/test_contract.py}、以及 {@code tools/check_contract.py}
 * 共用同一份黄金样本 {@code contracts/trip-plan.sample.json}。
 *
 * <p>断言口径与 {@code tools/check_contract.py --keys} 输出一致：
 * <b>整份响应 61 条路径</b>（含 {@code data}/{@code message}/{@code success} 与所有容器路径）；
 * 其中 {@code data} 子树是 58 条。
 */
class TripPlanContractTest {

    /**
     * 与运行中的应用同口径的 ObjectMapper：
     * {@code ALWAYS} 包含策略（application.yml 的 default-property-inclusion: always）
     * 与忽略未知字段（Agent 由 LLM 产出，可能多带字段）。
     */
    private static final ObjectMapper MAPPER = JsonMapper.builder()
            .serializationInclusion(JsonInclude.Include.ALWAYS)
            .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();

    /** 冻结契约的 61 条键路径（来源：tools/check_contract.py --keys contracts/trip-plan.sample.json）。 */
    private static final Set<String> FROZEN_RESPONSE_KEYS = Set.of(
            "success",
            "message",
            "data",
            "data.city",
            "data.start_date",
            "data.end_date",
            "data.days",
            "data.weather_info",
            "data.overall_suggestions",
            "data.budget",
            "data.budget.total_attractions",
            "data.budget.total_hotels",
            "data.budget.total_meals",
            "data.budget.total_transportation",
            "data.budget.total",
            "data.days[].date",
            "data.days[].day_index",
            "data.days[].description",
            "data.days[].transportation",
            "data.days[].accommodation",
            "data.days[].hotel",
            "data.days[].hotel.name",
            "data.days[].hotel.address",
            "data.days[].hotel.location",
            "data.days[].hotel.location.longitude",
            "data.days[].hotel.location.latitude",
            "data.days[].hotel.price_range",
            "data.days[].hotel.rating",
            "data.days[].hotel.distance",
            "data.days[].hotel.type",
            "data.days[].hotel.estimated_cost",
            "data.days[].attractions",
            "data.days[].attractions[].name",
            "data.days[].attractions[].address",
            "data.days[].attractions[].location",
            "data.days[].attractions[].location.longitude",
            "data.days[].attractions[].location.latitude",
            "data.days[].attractions[].visit_duration",
            "data.days[].attractions[].description",
            "data.days[].attractions[].category",
            "data.days[].attractions[].rating",
            "data.days[].attractions[].photos",
            "data.days[].attractions[].poi_id",
            "data.days[].attractions[].image_url",
            "data.days[].attractions[].ticket_price",
            "data.days[].meals",
            "data.days[].meals[].type",
            "data.days[].meals[].name",
            "data.days[].meals[].address",
            "data.days[].meals[].location",
            "data.days[].meals[].location.longitude",
            "data.days[].meals[].location.latitude",
            "data.days[].meals[].description",
            "data.days[].meals[].estimated_cost",
            "data.weather_info[].date",
            "data.weather_info[].day_weather",
            "data.weather_info[].night_weather",
            "data.weather_info[].day_temp",
            "data.weather_info[].night_temp",
            "data.weather_info[].wind_direction",
            "data.weather_info[].wind_power");

    @Test
    @DisplayName("黄金样本往返序列化后键集合必须等于 61 条冻结契约")
    void goldenFixtureRoundTripsToFrozenKeySet() throws Exception {
        JsonNode golden = fixture("trip-plan.sample.json");
        assertThat(flatten(golden))
                .as("黄金样本本身的键集合应先与冻结契约一致（若这里失败，是 contracts 被改了）")
                .containsExactlyInAnyOrderElementsOf(FROZEN_RESPONSE_KEYS);

        TripPlanResponseDto dto = MAPPER.treeToValue(golden, TripPlanResponseDto.class);
        JsonNode roundTrip = MAPPER.valueToTree(dto);

        assertThat(flatten(roundTrip))
                .as("DTO 往返后的键集合必须与冻结契约完全一致（多/少一个键都会让前端出错或字段被丢弃）")
                .containsExactlyInAnyOrderElementsOf(FROZEN_RESPONSE_KEYS);

        assertThat(flatten(roundTrip.path("data")))
                .as("data 子树应为 58 条（61 条去掉 success/message/data）")
                .hasSize(58);
    }

    @Test
    @DisplayName("snake_case 映射必须真的读到值：字段名写错时不能只是变成 null")
    void snakeCaseFieldsAreActuallyMapped() throws Exception {
        TripPlanResponseDto dto = MAPPER.readValue(fixtureFile("trip-plan.sample.json").toFile(), TripPlanResponseDto.class);

        assertThat(dto.success()).isTrue();
        assertThat(dto.data().startDate()).isEqualTo("2026-10-10");
        assertThat(dto.data().days()).hasSize(1);

        var day = dto.data().days().get(0);
        assertThat(day.dayIndex()).isZero();
        assertThat(day.transportation()).isEqualTo("公共交通");
        assertThat(day.hotel().priceRange()).isEqualTo("400-600元");
        assertThat(day.hotel().rating()).isEqualTo("4.6");           // hotel.rating 必须是字符串
        assertThat(day.attractions().get(0).visitDuration()).isEqualTo(180);
        assertThat(day.attractions().get(0).location().longitude()).isEqualTo(120.130396);
        assertThat(day.attractions().get(0).ticketPrice()).isZero();
        assertThat(day.meals()).hasSize(3);
        assertThat(dto.data().weatherInfo().get(0).dayTemp()).isEqualTo(25);   // 温度必须是数字
        assertThat(dto.data().budget().totalTransportation()).isEqualTo(40);
        assertThat(dto.data().overallSuggestions()).isNotBlank();
    }

    @Test
    @DisplayName("可空性红线：days / attractions / meals 恒非 null（前端直接 .forEach）")
    void collectionsRedLinesAreNotNull() throws Exception {
        TripPlanResponseDto dto = MAPPER.readValue(fixtureFile("trip-plan.sample.json").toFile(), TripPlanResponseDto.class);

        assertThat(dto.data().days()).isNotNull();
        assertThat(dto.data().days().get(0).attractions()).isNotNull();
        assertThat(dto.data().days().get(0).meals()).isNotNull();
    }

    @Test
    @DisplayName("温度带单位必须反序列化失败（防止 Integer 被写成 String 还悄悄通过）")
    void temperatureWithUnitMustFail() throws Exception {
        JsonNode golden = fixture("trip-plan.sample.json");
        ((com.fasterxml.jackson.databind.node.ObjectNode) golden.path("data").path("weather_info").get(0))
                .put("day_temp", "25°C");

        assertThatThrownBy(() -> MAPPER.treeToValue(golden, TripPlanResponseDto.class))
                .as("day_temp=25°C 必须失败：前端渲染 {{ day_temp }}°C，允许它通过就会显示 25°C°C")
                .isInstanceOf(JsonProcessingException.class);
    }

    @Test
    @DisplayName("Agent 返回结构不可用的 JSON 必须被 502 拦下（不能让 days=null 流到前端）")
    void structurallyBrokenPlanMustBeRejected() {
        // 真实场景：Agent 返回了一个合法 JSON 但结构不对的对象（例如 {"probe":true}），
        // Jackson 会把未知字段忽略、其余字段全留 null，于是 days=null。
        // 前端 Result.vue:433/824 对 days 直接 .forEach 且无判空 —— 必须在 BFF 就拦下。
        com.helloagents.travel.dto.TripPlanDto broken = new com.helloagents.travel.dto.TripPlanDto(
                "杭州", "2026-10-10", "2026-10-10", null, java.util.List.of(), "建议", null);

        assertThatThrownBy(() -> com.helloagents.travel.client.AgentClient
                .requireStructurallyUsable(broken, "trace-test"))
                .as("days=null 是前端崩溃红线，必须 502 AGENT_BAD_RESPONSE")
                .isInstanceOf(com.helloagents.travel.support.ApiException.class)
                .satisfies(ex -> {
                    var api = (com.helloagents.travel.support.ApiException) ex;
                    assertThat(api.getStatus()).isEqualTo(502);
                    assertThat(api.getCode()).isEqualTo("AGENT_BAD_RESPONSE");
                });
    }

    // ---------------------------------------------------------------- 工具方法

    /** 向上查找 contracts 目录，避免写死绝对路径（maven 以模块目录为工作目录）。 */
    private static Path fixtureFile(String name) {
        Path dir = Paths.get("").toAbsolutePath();
        for (int depth = 0; depth < 6 && dir != null; depth++, dir = dir.getParent()) {
            Path candidate = dir.resolve("contracts").resolve(name);
            if (Files.isRegularFile(candidate)) {
                return candidate;
            }
        }
        throw new IllegalStateException(
                "未找到 contracts/" + name + "（从 " + Paths.get("").toAbsolutePath() + " 向上查找 6 层仍未命中）");
    }

    private static JsonNode fixture(String name) throws Exception {
        // 注意：本版本 Jackson 的 ObjectMapper 没有 readTree(Path) 重载，必须转 File
        return MAPPER.readTree(fixtureFile(name).toFile());
    }

    /**
     * 与 tools/check_contract.py 的 flatten_paths 同语义：每个节点路径都记录（含容器），
     * 列表元素折叠为 {@code []}，空列表只留字段路径本身。
     */
    private static Set<String> flatten(JsonNode node) {
        Set<String> paths = new TreeSet<>();
        collect(node, "", paths);
        return paths;
    }

    private static void collect(JsonNode node, String path, Set<String> paths) {
        if (node == null) {
            return;
        }
        if (node.isObject()) {
            node.fields().forEachRemaining(entry -> {
                String child = path.isEmpty() ? entry.getKey() : path + "." + entry.getKey();
                paths.add(child);
                collect(entry.getValue(), child, paths);
            });
        } else if (node.isArray() && !node.isEmpty()) {
            collect(node.get(0), path + "[]", paths);
        }
    }
}
