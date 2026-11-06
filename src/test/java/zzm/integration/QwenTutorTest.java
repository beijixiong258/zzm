package zzm.integration;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;
import zzm.config.AppProperties;
import zzm.service.ContextBudget;
import cn.hutool.json.*;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.jupiter.api.Assertions.*;

class QwenTutorTest {
    @Test void exhaustedTurnBudgetRejectsBeforeCallingProvider() {
        AppProperties properties = new AppProperties(); properties.getTutor().setTurnInputLimit(100);
        var client = new QwenClient(properties, new ContextBudget());
        var failure = assertThrows(org.springframework.web.server.ResponseStatusException.class,
            () -> client.completeTutor(List.of(new UserMessage("Continue")), List.of(), List::of, () -> 0, () -> {}, 20, 100));
        assertEquals(422, failure.getStatusCode().value());
    }
    @Test void expiredTurnRejectsBeforeCallingProvider() {
        var client = new QwenClient(new AppProperties(), new ContextBudget());
        var failure = assertThrows(org.springframework.web.server.ResponseStatusException.class,
            () -> client.completeTutor(List.of(new UserMessage("Continue")), List.of(), List::of, () -> 0, () -> {}, 0, 0));
        assertEquals(504, failure.getStatusCode().value());
    }
    @Test void toolRoundTripsAreBoundedAndUsageIsAccumulated() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        AtomicInteger requests = new AtomicInteger(), reads = new AtomicInteger();
        List<JSONObject> received = new ArrayList<>();
        server.createContext("/v1/chat/completions", exchange -> {
            received.add(JSONUtil.parseObj(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8)));
            boolean first = requests.incrementAndGet() == 1;
            String message = first ? "{\"role\":\"assistant\",\"content\":null,\"tool_calls\":[{\"id\":\"read1\",\"type\":\"function\",\"function\":{\"name\":\"read_source\",\"arguments\":\"{}\"}},{\"id\":\"read2\",\"type\":\"function\",\"function\":{\"name\":\"read_source\",\"arguments\":\"{}\"}}]}"
                : "{\"role\":\"assistant\",\"content\":\"A grounded answer\"}";
            byte[] bytes = ("{\"id\":\"test\",\"object\":\"chat.completion\",\"created\":1,\"model\":\"test\",\"choices\":[{\"index\":0,\"message\":" + message
                + ",\"finish_reason\":\"" + (first ? "tool_calls" : "stop") + "\"}],\"usage\":{\"prompt_tokens\":20,\"completion_tokens\":5,\"total_tokens\":25}}").getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json"); exchange.sendResponseHeaders(200, bytes.length); exchange.getResponseBody().write(bytes); exchange.close();
        });
        server.start();
        try {
            AppProperties properties = new AppProperties(); properties.getAi().setProvider("test"); properties.getAi().setApiKey("test-key");
            properties.getAi().setBaseUrl("http://127.0.0.1:" + server.getAddress().getPort()); properties.getAi().setModel("test");
            QwenClient client = new QwenClient(properties, new ContextBudget());
            ToolCallback tool = new ToolCallback() {
                public ToolDefinition getToolDefinition() { return ToolDefinition.builder().name("read_source").description("读取授权材料").inputSchema("{\"type\":\"object\",\"properties\":{}}").build(); }
                public String call(String arguments) { reads.incrementAndGet(); return "trusted-source"; }
            };
            var result = client.completeTutor(List.of(new UserMessage("Explain the source")), List.of(tool), List::of, () -> 0, () -> {});
            assertEquals("A grounded answer", result.text()); assertEquals(1, reads.get()); assertEquals(2, requests.get());
            assertEquals(40L, result.usage().get("promptTokensActual")); assertEquals(10L, result.usage().get("completionTokensActual"));
            assertTrue(received.get(1).getJSONArray("messages").toString().contains("trusted-source"));
        } finally { server.stop(0); }
    }
}
