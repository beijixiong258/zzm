package zzm.service;

import org.springframework.ai.chat.messages.Message;
import org.springframework.stereotype.Service;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Local estimates are advisory; only the provider decides request capacity. */
@Service
public class ContextBudget {
    public static final int WINDOW = 256000;
    public static final int INPUT_LIMIT = 200000;
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
        long estimate = images, upper = images;
        for (Message message : messages) {
            estimate += estimate(message.getText()) + 32;
            upper += upperBound(message.getText()) + 32;
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("window", WINDOW); result.put("inputLimit", INPUT_LIMIT); result.put("inputEstimate", estimate);
        result.put("inputUpperBound", upper); result.put("imageEstimate", images);
        result.put("outputReserve", output); result.put("safetyReserve", safetyReserve);
        long inputRemaining = INPUT_LIMIT - upper, contextRemaining = WINDOW - upper - output - safetyReserve;
        result.put("inputRemaining", inputRemaining); result.put("contextRemaining", contextRemaining);
        result.put("remaining", Math.min(inputRemaining, contextRemaining));
        result.put("tokenEstimateOnly", true);
        result.put("estimatedOverReference", inputRemaining < 0 || contextRemaining < 0);
        result.put("method", "UTF-8 text upper bound; SiliconFlow Qwen high-detail image estimate; provider usage is authoritative");
        return result;
    }
}
