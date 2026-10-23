package cn.aicademiya.integration;

import cn.aicademiya.config.AppProperties;
import cn.aicademiya.service.ContextBudget;
import cn.hutool.json.*;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.http.client.reactive.JdkClientHttpConnector;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.openai.*;
import org.springframework.ai.openai.api.OpenAiApi;
import org.springframework.ai.retry.NonTransientAiException;
import org.springframework.ai.retry.TransientAiException;
import org.springframework.http.HttpMethod;
import org.springframework.http.client.*;
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
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import static cn.aicademiya.exception.ApiErrors.error;

@Slf4j
@Component
@RequiredArgsConstructor
public class QwenClient {
    private final AppProperties properties;
    private final ContextBudget budget;
    private final Semaphore slots = new Semaphore(4, true);
    public record Completion(String text, Map<String, Object> usage) {}
    public String complete(List<Message> messages) { return complete(messages, 4096, false, 0).text(); }
    public Completion complete(List<Message> messages, int output, boolean json, int images) {
        return complete(messages, output, json, images, ignored -> {});
    }
    public Completion complete(List<Message> messages, int output, boolean json, int images, int safetyReserve) {
        return complete(messages, output, json, images, safetyReserve, ignored -> {});
    }
    public Completion complete(List<Message> messages, int output, boolean json, int images, java.util.function.IntConsumer progress) {
        return complete(messages, output, json, images, ContextBudget.SAFETY, progress);
    }
    private Completion complete(List<Message> messages, int output, boolean json, int images, int safetyReserve, java.util.function.IntConsumer progress) {
        Map<String, Object> measurement = budget.require(messages, output, images, safetyReserve);
        boolean acquired = false;
        try {
            acquired = slots.tryAcquire(10, TimeUnit.SECONDS);
            if (!acquired) throw error(429, "All AI request slots are busy. Your work is saved; try again shortly.");
            ChatResponse response;
            String text;
            String finish;
            if (output >= 8192) {
                // Consume long responses incrementally so a healthy generation does not hit a first-byte timeout.
                StringBuilder content = new StringBuilder();
                ChatResponse[] last = new ChatResponse[1];
                String[] reason = new String[1];
                int idleTimeout = Math.max(30, configuration().getInt("timeout_seconds", 180));
                reactor.core.publisher.Flux.defer(() -> {
                        content.setLength(0); last[0] = null; reason[0] = null; progress.accept(0);
                        return client(output, json).prompt(new Prompt(messages)).stream().chatResponse();
                    }).timeout(reactor.core.publisher.Mono.delay(Duration.ofMinutes(5)),
                        chunk -> reactor.core.publisher.Mono.delay(Duration.ofSeconds(idleTimeout)))
                    .doOnNext(chunk -> {
                        last[0] = chunk;
                        if (chunk.getResult() != null) {
                            String delta = chunk.getResult().getOutput().getText();
                            if (delta != null) { content.append(delta); progress.accept(content.length()); }
                            String ending = chunk.getResult().getMetadata().getFinishReason();
                            if (ending != null && !ending.isBlank()) reason[0] = ending;
                        }
                    }).takeUntil(chunk -> reason[0] != null && chunk.getMetadata() != null
                        && chunk.getMetadata().getUsage() != null && chunk.getMetadata().getUsage().getPromptTokens() > 0)
                    .retryWhen(reactor.util.retry.Retry.backoff(1, Duration.ofSeconds(2))
                        .filter(this::retryableStreamFailure).onRetryExhaustedThrow((spec, signal) -> signal.failure()))
                    .blockLast(Duration.ofMinutes(20));
                response = last[0]; text = content.toString(); finish = reason[0];
                if (finish == null) throw error(502, "AI response ended before completion. Retry generation.");
            } else {
                response = client(output, json).prompt(new Prompt(messages)).call().chatResponse();
                if (response == null || response.getResult() == null) throw error(502, "AI returned an empty response");
                text = response.getResult().getOutput().getText();
                finish = response.getResult().getMetadata().getFinishReason();
            }
            if (response == null) throw error(502, "AI returned an empty response");
            if ("length".equalsIgnoreCase(finish)) throw error(502, "AI response was truncated. Reduce the material size and retry.");
            if ("content_filter".equalsIgnoreCase(finish)) throw error(502, "AI could not process this content. Check the selected material.");
            if (text == null || text.isBlank()) throw error(502, "AI returned an empty response");
            if (response.getMetadata() != null && response.getMetadata().getUsage() != null) {
                var usage = response.getMetadata().getUsage();
                measurement.put("promptTokensActual", usage.getPromptTokens());
                measurement.put("completionTokensActual", usage.getCompletionTokens());
                measurement.put("totalTokensActual", usage.getTotalTokens());
            }
            measurement.put("charactersReceived", text.length());
            return new Completion(text, measurement);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt(); throw error(503, "AI request was interrupted. Try again when ready.");
        } catch (ResponseStatusException exception) { throw exception;
        } catch (NonTransientAiException exception) { throw error(502, exception.getMessage());
        } catch (org.springframework.web.reactive.function.client.WebClientResponseException exception) {
            int status = exception.getStatusCode().value();
            String detail = switch (status) {
                case 401, 403 -> "AI authentication failed. Check the API key and model permissions.";
                case 404 -> "AI model or API endpoint was not found. Check the configuration.";
                case 413 -> "AI request is too large. Reduce the material or image size.";
                case 429 -> "All AI request slots are busy. Your work is saved; try again shortly.";
                default -> status >= 500 ? "AI service is temporarily unavailable. Your work is saved; try again shortly."
                    : "AI rejected the request (HTTP " + status + "). Check the model input format and context limit.";
            };
            log.warn("AI streaming request failed (HTTP {})", status);
            throw error(502, detail);
        } catch (RuntimeException exception) {
            log.warn("AI request failed: {} (cause: {})", exception.getClass().getSimpleName(),
                exception.getCause() == null ? "none" : exception.getCause().getClass().getSimpleName());
            throw error(502, "AI connection timed out or the service is unavailable after limited retries. Check the connection and try again.");
        } finally { if (acquired) slots.release(); }
    }
    public JSONObject configuration() {
        try {
            Path path = Path.of(properties.getConfigPath());
            JSONObject config = Files.isRegularFile(path) ? JSONUtil.parseObj(Files.readString(path, StandardCharsets.UTF_8).replace("\uFEFF", "")).getJSONObject("ai") : null;
            return config == null ? new JSONObject() : config;
        } catch (IOException | JSONException exception) { throw error(503, "AI configuration could not be read"); }
    }
    public Map<String, Object> status() {
        JSONObject ai = configuration();
        return Map.of("model", environment("AICADEMIYA_AI_MODEL", ai.getStr("model", "Qwen/Qwen3.8-27B")),
            "configured", !environment("AICADEMIYA_AI_API_KEY", ai.getStr("api_key", "")).isBlank(),
            "contextWindow", ContextBudget.WINDOW, "inputLimit", ContextBudget.INPUT_LIMIT, "safetyReserve", ContextBudget.SAFETY);
    }
    private ChatClient client(int output, boolean json) {
        JSONObject ai = configuration();
        String key = environment("AICADEMIYA_AI_API_KEY", ai.getStr("api_key", ""));
        String base = environment("AICADEMIYA_AI_BASE_URL", ai.getStr("base_url", "https://api.siliconflow.cn/v1")).replaceAll("/+$", "");
        String model = environment("AICADEMIYA_AI_MODEL", ai.getStr("model", "Qwen/Qwen3.8-27B"));
        if (key.isBlank() || model.isBlank()) throw error(503, "Configure the AI API key and model before generating content");
        if (base.endsWith("/v1")) base = base.substring(0, base.length() - 3);
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setProxy(java.net.Proxy.NO_PROXY);
        factory.setConnectTimeout(Duration.ofSeconds(15));
        factory.setReadTimeout(Duration.ofSeconds(Math.max(10, ai.getInt("timeout_seconds", 180))));
        java.net.ProxySelector direct = new java.net.ProxySelector() {
            @Override public List<java.net.Proxy> select(URI uri) { return List.of(java.net.Proxy.NO_PROXY); }
            @Override public void connectFailed(URI uri, java.net.SocketAddress address, IOException exception) {}
        };
        var httpClient = java.net.http.HttpClient.newBuilder().proxy(direct)
            .connectTimeout(Duration.ofSeconds(15)).build();
        OpenAiApi api = OpenAiApi.builder().baseUrl(base).apiKey(key)
            .webClientBuilder(WebClient.builder().clientConnector(new JdkClientHttpConnector(httpClient))
                .codecs(codecs -> codecs.defaultCodecs().maxInMemorySize(4 * 1024 * 1024)))
            .restClientBuilder(RestClient.builder().requestFactory(factory))
            .responseErrorHandler(new ResponseErrorHandler() {
                @Override public boolean hasError(ClientHttpResponse response) throws IOException { return response.getStatusCode().isError(); }
                @Override public void handleError(URI url, HttpMethod method, ClientHttpResponse response) throws IOException {
                    int status = response.getStatusCode().value();
                    if (status == 429 || status >= 500) throw new TransientAiException("AI service is busy (HTTP " + status + ")");
                    String detail = switch (status) {
                        case 401, 403 -> "AI authentication failed. Check the API key and model permissions.";
                        case 404 -> "AI model or API endpoint was not found. Check the configuration.";
                        case 413 -> "AI request is too large. Reduce the material or image size.";
                        default -> "AI rejected the request (HTTP " + status + "). Check the model input format and context limit.";
                    };
                    throw new NonTransientAiException(detail);
                }
            }).build();
        OpenAiChatOptions.Builder options = OpenAiChatOptions.builder().model(model)
            .temperature(ai.getDouble("temperature", 0.3)).maxTokens(output).streamUsage(true);
        Map<String, Object> extra = new LinkedHashMap<>();
        if ("siliconflow".equals(ai.getStr("provider", "siliconflow"))) extra.put("enable_thinking", false);
        if (json) extra.put("response_format", Map.of("type", "json_object"));
        options.extraBody(extra);
        RetryTemplate retry = RetryTemplate.builder().maxAttempts(2)
            .retryOn(TransientAiException.class).retryOn(ResourceAccessException.class)
            .exponentialBackoff(Duration.ofSeconds(1), 2, Duration.ofSeconds(3)).build();
        return ChatClient.create(OpenAiChatModel.builder().openAiApi(api).defaultOptions(options.build()).retryTemplate(retry).build());
    }
    private boolean retryableStreamFailure(Throwable failure) {
        if (failure instanceof org.springframework.web.reactive.function.client.WebClientResponseException response)
            return response.getStatusCode().value() == 429 || response.getStatusCode().is5xxServerError();
        return failure instanceof TransientAiException || failure instanceof ResourceAccessException
            || failure instanceof org.springframework.web.reactive.function.client.WebClientRequestException
            || failure instanceof java.util.concurrent.TimeoutException || failure instanceof IOException;
    }
    private String environment(String key, String fallback) {
        String value = System.getenv(key); return value == null || value.isBlank() ? fallback : value;
    }
}
