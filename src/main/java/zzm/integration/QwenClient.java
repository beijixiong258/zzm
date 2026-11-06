package zzm.integration;

import zzm.config.AppProperties;
import zzm.service.ContextBudget;
import cn.hutool.json.*;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.http.client.reactive.JdkClientHttpConnector;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.ToolResponseMessage;
import org.springframework.ai.tool.ToolCallback;
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
import java.time.Duration;
import java.util.*;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import static zzm.exception.ApiErrors.error;

@Slf4j
@Component
@RequiredArgsConstructor
public class QwenClient {
    private static final int CONNECTION_CHECK_TIMEOUT_SECONDS = 15;
    private static final String CONNECTION_CHECK_TIMEOUT = "The connection check timed out after 15 seconds. Try again shortly.";
    private static final String CONNECTION_CHECK_INCOMPLETE = "The connection check returned no complete reply. Try again shortly.";
    private final AppProperties properties;
    private final ContextBudget budget;
    private final Semaphore slots = new Semaphore(4, true);
    public record Completion(String text, Map<String, Object> usage) {}
    /** 显式执行只读工具循环，每次模型往返重新核对权限、预算和累计用量。 */
    public Completion completeTutor(List<Message> initial, List<ToolCallback> callbacks,
            java.util.function.Supplier<List<Message>> pendingImages, java.util.function.IntSupplier imageTokens, Runnable validate) {
        return completeTutor(initial, callbacks, pendingImages, imageTokens, validate, properties.getTutor().getTimeoutSeconds(), 0);
    }
    public Completion completeTutor(List<Message> initial, List<ToolCallback> callbacks,
            java.util.function.Supplier<List<Message>> pendingImages, java.util.function.IntSupplier imageTokens, Runnable validate,
            int seconds, long earlierInput) {
        return completeTutor(initial, callbacks, pendingImages, imageTokens, validate, seconds, earlierInput, outputTokens("chat", 4096), false);
    }
    public Completion completeSummary(List<Message> messages, int output, int seconds) {
        return completeTutor(messages, List.of(), List::of, () -> 0, () -> {}, Math.min(25, seconds), 0, output, true);
    }
    private Completion completeTutor(List<Message> initial, List<ToolCallback> callbacks,
            java.util.function.Supplier<List<Message>> pendingImages, java.util.function.IntSupplier imageTokens, Runnable validate,
            int seconds, long earlierInput, int output, boolean json) {
        var limits = properties.getTutor();
        int calls = 0;
        long started = System.nanoTime(), actualInput = 0, actualOutput = 0, estimatedTotal = earlierInput;
        boolean acquired = false;
        List<Message> messages = new ArrayList<>(initial);
        List<Map<String, Object>> rounds = new ArrayList<>();
        Set<String> performed = new HashSet<>();
        Map<String, ToolCallback> tools = new LinkedHashMap<>(); callbacks.forEach(c -> tools.put(c.getToolDefinition().name(), c));
        int schemaTokens = callbacks.stream().mapToInt(c -> budget.upperBound(c.getToolDefinition().inputSchema()) + budget.upperBound(c.getToolDefinition().description()) + 64).sum();
        int maximumCalls = Math.max(1, Math.min(16, limits.getToolCalls()));
        int maximumRounds = Math.max(0, Math.min(4, limits.getToolRounds()));
        long cumulativeLimit = limits.getTurnInputLimit();
        try {
            acquired = slots.tryAcquire(10, TimeUnit.SECONDS);
            if (!acquired) throw error(429, "All AI request slots are busy. Try again shortly.");
            for (int round = 0; round <= maximumRounds; round++) {
                validate.run();
                int remainingSeconds = seconds - (int) TimeUnit.NANOSECONDS.toSeconds(System.nanoTime() - started);
                if (remainingSeconds <= 0) throw error(504, "The tutor reached its time limit. Narrow the question and try again.");
                boolean useTools = !callbacks.isEmpty() && round < maximumRounds && calls < maximumCalls
                    && estimatedTotal + 2L * (budget.tokens(messages) + schemaTokens + imageTokens.getAsInt()) <= cumulativeLimit;
                var measurement = budget.studentDescribe(messages, limits, output, imageTokens.getAsInt(), useTools ? schemaTokens : 0);
                long estimated = ((Number) measurement.get("inputEstimate")).longValue();
                if (Boolean.TRUE.equals(measurement.get("estimatedOverReference")))
                    throw error(422, "The required tutor context exceeds the configured model limit. Narrow the question or shorten the required instructions.");
                if (estimatedTotal + estimated > cumulativeLimit) throw error(422, "The tutor reached its reading budget. Ask about a smaller part of the task.");
                estimatedTotal += estimated;
                long requestStart = System.nanoTime();
                ChatResponse response = client(output, json, useTools ? callbacks : List.of(), Math.max(1, remainingSeconds), true)
                    .prompt(new Prompt(messages)).call().chatResponse();
                if (TimeUnit.NANOSECONDS.toSeconds(System.nanoTime() - started) >= seconds)
                    throw error(504, "The tutor reached its time limit. Narrow the question and try again.");
                if (response == null || response.getResult() == null) throw error(502, "AI returned an empty response");
                String finish = response.getResult().getMetadata().getFinishReason();
                if ("length".equalsIgnoreCase(finish) || "content_filter".equalsIgnoreCase(finish))
                    throw error(502, "The tutor response was not completed. No partial reply was saved.");
                var usage = response.getMetadata() == null ? null : response.getMetadata().getUsage();
                long input = usage == null ? 0 : usage.getPromptTokens(), completion = usage == null ? 0 : usage.getCompletionTokens();
                actualInput += input; actualOutput += completion;
                estimatedTotal = Math.max(estimatedTotal, earlierInput + actualInput);
                rounds.add(Map.of("input", input, "output", completion, "inputEstimate", estimated,
                    "requestMs", TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - requestStart)));
                var answer = response.getResult().getOutput();
                if (answer.getToolCalls().isEmpty()) {
                    if (answer.getText() == null || answer.getText().isBlank()) throw error(502, "AI returned an empty response");
                    validate.run();
                    measurement.put("promptTokensActual", actualInput); measurement.put("completionTokensActual", actualOutput);
                    measurement.put("totalTokensActual", actualInput + actualOutput); measurement.put("turnInputEstimate", estimatedTotal);
                    measurement.put("toolCalls", calls); measurement.put("modelRounds", rounds);
                    measurement.put("requestTiming", Map.of("requestMs", TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started)));
                    return new Completion(answer.getText(), measurement);
                }
                if (!useTools) throw error(502, "The model did not finish within the tutor tool budget. Try a more specific question.");
                messages.add(answer);
                List<ToolResponseMessage.ToolResponse> responses = new ArrayList<>();
                for (var call : answer.getToolCalls()) {
                    if (TimeUnit.NANOSECONDS.toSeconds(System.nanoTime() - started) >= seconds)
                        throw error(504, "The tutor reached its time limit. Narrow the question and try again.");
                    validate.run();
                    ToolCallback callback = tools.get(call.name());
                    String key = call.name() + ":" + call.arguments(), value;
                    if (callback == null) value = "{\"error\":\"Unknown read-only tool\"}";
                    else if (calls >= maximumCalls) value = "{\"error\":\"Reading budget reached; answer using available evidence\"}";
                    else if (!performed.add(key)) value = "{\"error\":\"This exact read was already returned in this turn\"}";
                    else {
                        calls++;
                        try { value = callback.call(call.arguments()); }
                        catch (ResponseStatusException exception) { throw exception; }
                        catch (RuntimeException exception) { value = "{\"error\":\"Invalid tool arguments or unavailable source; correct the request or state the limitation\"}"; }
                    }
                    responses.add(new ToolResponseMessage.ToolResponse(call.id(), call.name(), value));
                }
                messages.add(ToolResponseMessage.builder().responses(responses).build());
                messages.addAll(pendingImages.get());
            }
            throw error(502, "The tutor did not produce a completed response");
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt(); throw error(503, "AI request was interrupted");
        } catch (ResponseStatusException exception) { throw exception; }
        catch (NonTransientAiException | TransientAiException exception) {
            log.warn("Tutor provider request failed: {}", exception.getMessage());
            throw error(502, exception.getMessage());
        } catch (RuntimeException exception) {
            log.warn("Tutor request failed", exception);
            throw error(502, "The tutor request failed. No incomplete result was saved. Try again shortly.");
        }
        finally { if (acquired) slots.release(); }
    }
    /** 连接检测单次执行且不排队，以请求总时限约束连接、响应头和响应体的等待。 */
    public Completion checkConnection(List<Message> messages, int images) {
        if (!slots.tryAcquire()) throw error(429, "AI requests are busy. Try the connection check again shortly.");
        long started = System.nanoTime();
        boolean completed = false;
        try {
            ChatResponse response = client(64, false, List.of(), CONNECTION_CHECK_TIMEOUT_SECONDS, false, true)
                .prompt(new Prompt(messages)).call().chatResponse();
            if (response == null || response.getResult() == null) throw error(502, CONNECTION_CHECK_INCOMPLETE);
            String text = response.getResult().getOutput().getText();
            String finish = response.getResult().getMetadata().getFinishReason();
            if (text == null || text.isBlank() || "length".equalsIgnoreCase(finish) || "content_filter".equalsIgnoreCase(finish))
                throw error(502, CONNECTION_CHECK_INCOMPLETE);
            Map<String, Object> measurement = budget.describe(messages, 64, images, ContextBudget.SAFETY);
            if (response.getMetadata() != null && response.getMetadata().getUsage() != null) {
                var usage = response.getMetadata().getUsage();
                measurement.put("promptTokensActual", usage.getPromptTokens());
                measurement.put("completionTokensActual", usage.getCompletionTokens());
                measurement.put("totalTokensActual", usage.getTotalTokens());
            }
            measurement.put("charactersReceived", text.length());
            measurement.put("requestTiming", Map.of("queueWaitMs", 0L,
                "requestMs", TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started), "streamRetries", 0));
            completed = true;
            return new Completion(text, measurement);
        } catch (ResponseStatusException exception) { throw exception;
        } catch (NonTransientAiException | TransientAiException exception) { throw error(502, exception.getMessage());
        } catch (RuntimeException exception) {
            boolean timedOut = TimeUnit.NANOSECONDS.toSeconds(System.nanoTime() - started) >= CONNECTION_CHECK_TIMEOUT_SECONDS;
            boolean networkFailure = false;
            Throwable root = exception;
            for (Throwable cause = exception; cause != null; cause = cause.getCause()) {
                root = cause;
                timedOut |= cause instanceof java.util.concurrent.TimeoutException
                    || cause instanceof java.net.SocketTimeoutException || cause instanceof java.net.http.HttpTimeoutException;
                networkFailure |= cause instanceof ResourceAccessException || cause instanceof IOException;
            }
            log.warn("AI connection check failed: {} (root cause: {})", exception.getClass().getSimpleName(), root.getClass().getSimpleName());
            if (timedOut) throw error(504, CONNECTION_CHECK_TIMEOUT);
            for (Throwable cause = exception; cause != null; cause = cause.getCause()) {
                if (cause instanceof NonTransientAiException || cause instanceof TransientAiException)
                    throw error(502, cause.getMessage());
            }
            throw error(502, networkFailure
                ? "The connection check could not reach the AI service. Check the network and try again."
                : CONNECTION_CHECK_INCOMPLETE);
        } finally {
            slots.release();
            log.info("AI connection check completed={}, requestMs={}", completed,
                TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started));
        }
    }
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
        Map<String, Object> measurement = budget.describe(messages, output, images, safetyReserve);
        long startedNanos = System.nanoTime(), requestStartedNanos = 0;
        AtomicLong firstResponseNanos = new AtomicLong();
        AtomicInteger streamAttempts = new AtomicInteger(), charactersReceived = new AtomicInteger();
        boolean acquired = false;
        boolean completed = false;
        try {
            acquired = slots.tryAcquire(10, TimeUnit.SECONDS);
            if (!acquired) throw error(429, "All AI request slots are busy. Your work is saved; try again shortly.");
            requestStartedNanos = System.nanoTime();
            ChatResponse response;
            String text;
            String finish;
            if (output >= 8192) {
                // 增量读取长响应，避免正常生成过程触发首字节等待超时。
                StringBuilder content = new StringBuilder();
                ChatResponse[] last = new ChatResponse[1];
                String[] reason = new String[1];
                int idleTimeout = Math.max(30, configuration().getTimeoutSeconds());
                reactor.core.publisher.Flux.defer(() -> {
                        streamAttempts.incrementAndGet();
                        content.setLength(0); last[0] = null; reason[0] = null; progress.accept(0);
                        return client(output, json).prompt(new Prompt(messages)).stream().chatResponse();
                    }).timeout(reactor.core.publisher.Mono.delay(Duration.ofMinutes(5)),
                        chunk -> reactor.core.publisher.Mono.delay(Duration.ofSeconds(idleTimeout)))
                    .doOnNext(chunk -> {
                        firstResponseNanos.compareAndSet(0, System.nanoTime());
                        last[0] = chunk;
                        if (chunk.getResult() != null) {
                            String delta = chunk.getResult().getOutput().getText();
                            if (delta != null) { content.append(delta); charactersReceived.set(content.length()); progress.accept(content.length()); }
                            String ending = chunk.getResult().getMetadata().getFinishReason();
                            if (ending != null && !ending.isBlank()) reason[0] = ending;
                        }
                    }).takeUntil(chunk -> reason[0] != null && chunk.getMetadata() != null
                        && chunk.getMetadata().getUsage() != null && chunk.getMetadata().getUsage().getPromptTokens() > 0)
                    // 已输出回答后重试会丢弃已有结果，并重复可能耗时较长的生成过程。
                    .retryWhen(reactor.util.retry.Retry.backoff(1, Duration.ofSeconds(2))
                        .filter(failure -> charactersReceived.get() == 0 && reason[0] == null && retryableStreamFailure(failure))
                        .onRetryExhaustedThrow((spec, signal) -> signal.failure()))
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
            if ("length".equalsIgnoreCase(finish)) throw error(502, "Upstream AI response was truncated (finish_reason=length). Check the model output token setting and retry.");
            if ("content_filter".equalsIgnoreCase(finish)) throw error(502, "AI could not process this content. Check the selected material.");
            if (text == null || text.isBlank()) throw error(502, "AI returned an empty response");
            if (response.getMetadata() != null && response.getMetadata().getUsage() != null) {
                var usage = response.getMetadata().getUsage();
                measurement.put("promptTokensActual", usage.getPromptTokens());
                measurement.put("completionTokensActual", usage.getCompletionTokens());
                measurement.put("totalTokensActual", usage.getTotalTokens());
            }
            measurement.put("charactersReceived", text.length());
            charactersReceived.set(text.length());
            Map<String, Object> timing = new LinkedHashMap<>();
            timing.put("queueWaitMs", TimeUnit.NANOSECONDS.toMillis(requestStartedNanos - startedNanos));
            timing.put("requestMs", TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - requestStartedNanos));
            if (firstResponseNanos.get() != 0)
                timing.put("firstResponseMs", TimeUnit.NANOSECONDS.toMillis(firstResponseNanos.get() - requestStartedNanos));
            timing.put("streamRetries", Math.max(0, streamAttempts.get() - 1));
            measurement.put("requestTiming", timing);
            completed = true;
            return new Completion(text, measurement);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt(); throw error(503, "AI request was interrupted. Try again when ready.");
        } catch (ResponseStatusException exception) { throw exception;
        } catch (NonTransientAiException | TransientAiException exception) { throw error(502, exception.getMessage());
        } catch (org.springframework.web.reactive.function.client.WebClientResponseException exception) {
            int status = exception.getStatusCode().value();
            log.warn("AI streaming request failed (HTTP {})", status);
            throw error(502, providerError(status, exception.getResponseBodyAsString()));
        } catch (RuntimeException exception) {
            for (Throwable cause = exception; cause != null; cause = cause.getCause()) {
                if (cause instanceof org.springframework.web.reactive.function.client.WebClientResponseException response)
                    throw error(502, providerError(response.getStatusCode().value(), response.getResponseBodyAsString()));
                if (cause instanceof NonTransientAiException || cause instanceof TransientAiException)
                    throw error(502, cause.getMessage());
                if (cause instanceof java.util.concurrent.TimeoutException || cause instanceof java.net.SocketTimeoutException)
                    throw error(504, "Upstream AI request timed out after limited retries. No incomplete result was applied.");
            }
            log.warn("AI request failed: {} (cause: {})", exception.getClass().getSimpleName(),
                exception.getCause() == null ? "none" : exception.getCause().getClass().getSimpleName());
            throw error(502, "AI connection or response processing failed (" + exception.getClass().getSimpleName() + "). No incomplete result was applied.");
        } finally {
            long finishedNanos = System.nanoTime();
            log.info("AI request completed={}, queueMs={}, requestMs={}, firstResponseMs={}, streamRetries={}, characters={}", completed,
                TimeUnit.NANOSECONDS.toMillis((requestStartedNanos == 0 ? finishedNanos : requestStartedNanos) - startedNanos),
                requestStartedNanos == 0 ? 0 : TimeUnit.NANOSECONDS.toMillis(finishedNanos - requestStartedNanos),
                firstResponseNanos.get() == 0 ? null : TimeUnit.NANOSECONDS.toMillis(firstResponseNanos.get() - requestStartedNanos),
                Math.max(0, streamAttempts.get() - 1), charactersReceived.get());
            if (acquired) slots.release();
        }
    }
    private String providerError(int status, String body) {
        String reason = Objects.toString(body, "").strip();
        try {
            JSONObject response = JSONUtil.parseObj(reason);
            Object detail = response.get("error");
            reason = detail instanceof JSONObject problem ? problem.getStr("message", problem.toString())
                : response.getStr("message", Objects.toString(detail, reason));
        } catch (RuntimeException ignored) { /* 保留服务提供方返回的非结构化诊断信息。 */ }
        String key = environment("AICADEMIYA_AI_API_KEY", configuration().getApiKey());
        if (!key.isBlank()) reason = reason.replace(key, "[redacted]");
        if (reason.length() > 2000) reason = reason.substring(0, 2000) + "…";
        if (reason.isBlank()) reason = status == 429 ? "Provider rate limit or quota exceeded." : "The provider rejected this request.";
        return "Upstream AI request failed (HTTP " + status + "): " + reason;
    }
    public int outputTokens(String operation, int fallback) {
        AppProperties.Ai ai = configuration();
        Integer configured = switch (operation) {
            case "vision" -> ai.getVisionMaxTokens();
            case "generation" -> ai.getGenerationMaxTokens();
            case "chat" -> ai.getChatMaxTokens();
            case "assistant" -> ai.getAssistantMaxTokens();
            default -> null;
        };
        int output = configured != null ? configured : ai.getMaxTokens() != null ? ai.getMaxTokens() : fallback;
        if (output < 1) throw error(422, "The configured AI output token limit must be positive.");
        return output;
    }
    private AppProperties.Ai configuration() { return properties.getAi(); }
    public Map<String, Object> status() {
        AppProperties.Ai ai = configuration();
        return Map.of("model", environment("AICADEMIYA_AI_MODEL", ai.getModel()),
            "configured", !environment("AICADEMIYA_AI_API_KEY", ai.getApiKey()).isBlank(),
            "contextWindow", ContextBudget.WINDOW, "inputLimit", ContextBudget.INPUT_LIMIT, "safetyReserve", ContextBudget.SAFETY,
            "tokenEstimateOnly", true);
    }
    private ChatClient client(int output, boolean json) {
        return client(output, json, List.of(), configuration().getTimeoutSeconds(), false);
    }
    private ChatClient client(int output, boolean json, List<ToolCallback> callbacks, int timeoutSeconds, boolean tutor) {
        return client(output, json, callbacks, timeoutSeconds, tutor, false);
    }
    private ChatClient client(int output, boolean json, List<ToolCallback> callbacks, int timeoutSeconds, boolean tutor, boolean connectionCheck) {
        AppProperties.Ai ai = configuration();
        String key = environment("AICADEMIYA_AI_API_KEY", ai.getApiKey());
        String base = environment("AICADEMIYA_AI_BASE_URL", ai.getBaseUrl()).replaceAll("/+$", "");
        String model = environment("AICADEMIYA_AI_MODEL", ai.getModel());
        if (key.isBlank() || model.isBlank()) throw error(503, "Configure the AI API key and model before generating content");
        if (base.endsWith("/v1")) base = base.substring(0, base.length() - 3);
        java.net.ProxySelector direct = new java.net.ProxySelector() {
            @Override public List<java.net.Proxy> select(URI uri) { return List.of(java.net.Proxy.NO_PROXY); }
            @Override public void connectFailed(URI uri, java.net.SocketAddress address, IOException exception) {}
        };
        var httpClient = java.net.http.HttpClient.newBuilder().proxy(direct)
            .connectTimeout(Duration.ofSeconds(15)).build();
        ClientHttpRequestFactory factory;
        if (connectionCheck) {
            JdkClientHttpRequestFactory bounded = new JdkClientHttpRequestFactory(httpClient);
            bounded.setReadTimeout(Duration.ofSeconds(CONNECTION_CHECK_TIMEOUT_SECONDS));
            factory = bounded;
        } else {
            SimpleClientHttpRequestFactory standard = new SimpleClientHttpRequestFactory();
            standard.setProxy(java.net.Proxy.NO_PROXY);
            standard.setConnectTimeout(Duration.ofSeconds(Math.min(15, Math.max(1, timeoutSeconds))));
            standard.setReadTimeout(Duration.ofSeconds(Math.max(1, timeoutSeconds)));
            factory = standard;
        }
        OpenAiApi api = OpenAiApi.builder().baseUrl(base).apiKey(key)
            .webClientBuilder(WebClient.builder().clientConnector(new JdkClientHttpConnector(httpClient))
                .codecs(codecs -> codecs.defaultCodecs().maxInMemorySize(4 * 1024 * 1024)))
            .restClientBuilder(RestClient.builder().requestFactory(factory))
            .responseErrorHandler(new ResponseErrorHandler() {
                @Override public boolean hasError(ClientHttpResponse response) throws IOException { return response.getStatusCode().isError(); }
                @Override public void handleError(URI url, HttpMethod method, ClientHttpResponse response) throws IOException {
                    int status = response.getStatusCode().value();
                    String detail = providerError(status, new String(response.getBody().readNBytes(8192), StandardCharsets.UTF_8));
                    if (status == 429 || status >= 500) throw new TransientAiException(detail);
                    throw new NonTransientAiException(detail);
                }
            }).build();
        OpenAiChatOptions.Builder options = OpenAiChatOptions.builder().model(model)
            .temperature(ai.getTemperature()).maxTokens(output);
        if (!connectionCheck) options.streamUsage(true);
        if (tutor) options.internalToolExecutionEnabled(false);
        if (!callbacks.isEmpty()) options.toolCallbacks(callbacks);
        Map<String, Object> extra = new LinkedHashMap<>();
        if ("siliconflow".equals(ai.getProvider())) extra.put("enable_thinking", false);
        if (json) extra.put("response_format", Map.of("type", "json_object"));
        options.extraBody(extra);
        RetryTemplate retry = RetryTemplate.builder().maxAttempts(tutor || connectionCheck ? 1 : 2)
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
