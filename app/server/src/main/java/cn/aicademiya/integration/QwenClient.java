package cn.aicademiya.integration;

import cn.aicademiya.config.AppProperties;
import cn.hutool.json.*;
import lombok.RequiredArgsConstructor;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.openai.*;
import org.springframework.ai.openai.api.OpenAiApi;
import org.springframework.ai.retry.NonTransientAiException;
import org.springframework.ai.retry.TransientAiException;
import org.springframework.http.HttpMethod;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.stereotype.Component;
import org.springframework.web.client.*;
import org.springframework.web.server.ResponseStatusException;
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import static cn.aicademiya.exception.ApiErrors.error;

@Component
@RequiredArgsConstructor
public class QwenClient {
    private final AppProperties properties;

    public String complete(List<Message> messages) {
        try {
            // Message objects preserve literal source text, JSON braces and image attachments.
            ChatResponse response = client().prompt(new Prompt(messages)).call().chatResponse();
            if (response == null || response.getResult() == null) throw error(502, "AI returned an empty response");
            String finishReason = response.getResult().getMetadata().getFinishReason();
            if ("length".equalsIgnoreCase(finishReason)) {
                throw error(502, "AI response was truncated. Reduce the material size and retry.");
            }
            if ("content_filter".equalsIgnoreCase(finishReason)) {
                throw error(502, "AI could not process this content. Check the selected material.");
            }
            String text = response.getResult().getOutput().getText();
            if (text == null || text.isBlank()) throw error(502, "AI returned an empty response");
            return text;
        } catch (ResponseStatusException exception) {
            throw exception;
        } catch (NonTransientAiException exception) {
            throw error(502, "AI rejected the request. Check the model configuration and supported input format.");
        } catch (RuntimeException exception) {
            throw error(502, "AI request failed after limited retries. Check the model connection and retry.");
        }
    }

    private ChatClient client() {
        JSONObject ai = new JSONObject();
        try {
            Path path = Path.of(properties.getConfigPath());
            if (Files.isRegularFile(path)) ai = JSONUtil.parseObj(Files.readString(path, StandardCharsets.UTF_8).replace("\uFEFF", "")).getJSONObject("ai");
        } catch (IOException | JSONException exception) {
            throw error(503, "AI configuration could not be read");
        }
        if (ai == null) ai = new JSONObject();
        String key = environment("AICADEMIYA_AI_API_KEY", ai.getStr("api_key", ""));
        String base = environment("AICADEMIYA_AI_BASE_URL", ai.getStr("base_url", "https://api.siliconflow.cn/v1"));
        String model = environment("AICADEMIYA_AI_MODEL", ai.getStr("model", "Qwen/Qwen3.8-27B"));
        if (key.isBlank() || model.isBlank()) throw error(503, "Configure the AI API key and model before generating content");
        base = base.replaceAll("/+$", "");
        if (base.endsWith("/v1")) base = base.substring(0, base.length() - 3);
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setProxy(java.net.Proxy.NO_PROXY);
        factory.setConnectTimeout(Duration.ofSeconds(15));
        factory.setReadTimeout(Duration.ofSeconds(Math.max(10, ai.getInt("timeout_seconds", 180))));
        OpenAiApi api = OpenAiApi.builder().baseUrl(base).apiKey(key)
            .restClientBuilder(RestClient.builder().requestFactory(factory))
            .responseErrorHandler(new ResponseErrorHandler() {
                @Override public boolean hasError(ClientHttpResponse response) throws IOException {
                    return response.getStatusCode().isError();
                }
                @Override public void handleError(URI url, HttpMethod method, ClientHttpResponse response) throws IOException {
                    int status = response.getStatusCode().value();
                    // Do not retain provider response bodies, which can echo uploaded text or configuration.
                    if (status == 429 || response.getStatusCode().is5xxServerError()) {
                        throw new TransientAiException("AI service temporarily unavailable: " + status);
                    }
                    throw new NonTransientAiException("AI request rejected: " + status);
                }
            }).build();
        OpenAiChatOptions.Builder options = OpenAiChatOptions.builder().model(model)
            .temperature(ai.getDouble("temperature", 0.3)).maxTokens(ai.getInt("max_tokens", 16384));
        if ("siliconflow".equals(ai.getStr("provider", "siliconflow"))) {
            Map<String, Object> extraBody = new LinkedHashMap<>();
            boolean thinking = ai.getBool("enable_thinking", false);
            extraBody.put("enable_thinking", thinking);
            if (thinking) extraBody.put("thinking_budget", ai.getInt("thinking_budget", 4096));
            options.extraBody(extraBody);
        }
        RetryTemplate retry = RetryTemplate.builder().maxAttempts(3)
            .retryOn(TransientAiException.class).retryOn(ResourceAccessException.class)
            .exponentialBackoff(Duration.ofSeconds(1), 2, Duration.ofSeconds(4)).build();
        return ChatClient.create(OpenAiChatModel.builder().openAiApi(api)
            .defaultOptions(options.build()).retryTemplate(retry).build());
    }

    private String environment(String key, String fallback) {
        String value = System.getenv(key);
        return value == null || value.isBlank() ? fallback : value;
    }
}
