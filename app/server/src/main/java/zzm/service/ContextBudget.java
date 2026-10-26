package zzm.service;

import org.springframework.ai.chat.messages.Message;
import org.springframework.stereotype.Service;
import java.nio.charset.StandardCharsets;
import java.util.*;
import static zzm.exception.ApiErrors.error;

/** Application budget, independent of a provider's larger advertised window. */
@Service
public class ContextBudget {
    public static final int WINDOW = 64000;
    public static final int INPUT_LIMIT = 40000;
    public static final int SAFETY = 10000;
    public static final int CHAT_SAFETY = 2048;
    public int upperBound(String text) {
        return text == null ? 0 : text.getBytes(StandardCharsets.UTF_8).length;
    }
    public int estimate(String text) {
        if (text == null || text.isEmpty()) return 0;
        long ascii = text.codePoints().filter(c -> c < 128).count();
        long other = text.codePointCount(0, text.length()) - ascii;
        return (int) Math.ceil(ascii / 3.5 + other * 1.5);
    }
    public int imageTokens(int width, int height) {
        // SiliconFlow Qwen high-detail estimate: 28-pixel grid, 3136..12845056 pixels.
        double w = Math.max(28, Math.ceil(width / 28.0) * 28);
        double h = Math.max(28, Math.ceil(height / 28.0) * 28);
        double area = w * h;
        if (area > 12845056 || area < 3136) {
            double ratio = Math.sqrt((area > 12845056 ? 12845056 : 3136) / area);
            w = Math.max(28, (area > 12845056 ? Math.floor(w * ratio / 28) : Math.ceil(w * ratio / 28)) * 28);
            h = Math.max(28, (area > 12845056 ? Math.floor(h * ratio / 28) : Math.ceil(h * ratio / 28)) * 28);
        }
        return (int) (w / 28 * (h / 28));
    }
    public Map<String, Object> describe(List<Message> messages, int output, int images) {
        return describe(messages, output, images, SAFETY);
    }
    public Map<String, Object> describe(List<Message> messages, int output, int images, int safetyReserve) {
        int estimate = images, upper = images;
        for (Message message : messages) {
            estimate += estimate(message.getText()) + 32;
            upper += upperBound(message.getText()) + 32;
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("window", WINDOW); result.put("inputLimit", INPUT_LIMIT); result.put("inputEstimate", estimate);
        result.put("inputUpperBound", upper); result.put("imageEstimate", images);
        result.put("outputReserve", output); result.put("safetyReserve", safetyReserve);
        int inputRemaining = INPUT_LIMIT - upper, contextRemaining = WINDOW - upper - output - safetyReserve;
        result.put("inputRemaining", inputRemaining); result.put("contextRemaining", contextRemaining);
        result.put("remaining", Math.min(inputRemaining, contextRemaining));
        result.put("allowed", inputRemaining >= 0 && contextRemaining >= 0);
        result.put("method", "UTF-8 text upper bound; SiliconFlow Qwen high-detail image estimate; provider usage is authoritative");
        return result;
    }
    public int generationOutput(List<Message> messages, int images) {
        int input = images + messages.stream().mapToInt(message -> upperBound(message.getText()) + 32).sum();
        // Preserve all input and the safety reserve; fail normally if even the minimum output cannot fit.
        return Math.min(16000, Math.max(8192, WINDOW - input - SAFETY));
    }
    public int replyOutput(List<Message> messages, int images) {
        int input = images + messages.stream().mapToInt(message -> upperBound(message.getText()) + 32).sum();
        return Math.min(4096, Math.max(1024, WINDOW - input - CHAT_SAFETY));
    }
    public Map<String, Object> require(List<Message> messages, int output, int images, int safetyReserve) {
        Map<String, Object> result = describe(messages, output, images, safetyReserve);
        if ((int) result.get("inputRemaining") < 0) throw error(422,
            "The estimated input exceeds the 40,000-token limit. Select fewer materials, split the task, or start a new conversation. No content was silently removed.");
        if (!Boolean.TRUE.equals(result.get("allowed"))) throw error(422,
            "Input, reserved output and the safety buffer exceed the 64,000-token context window. Select fewer materials or split the task. No content was silently removed.");
        return result;
    }
}
