package zzm.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;
import java.util.List;

@Data
@Component
@ConfigurationProperties(prefix = "app")
public class AppProperties {
    private Ai ai = new Ai();
    private String uploadDir;
    private int documentMaxUnits = 300;
    private int documentMaxCharacters = 300000;
    private int documentImageMaxEdge = 2000;
    private List<String> allowedOrigins;
    private boolean cookieSecure;
    private boolean demoEnabled;
    private int historyMaxAnswers = 50;
    private int historyMaxConversations = 10;
    private int historyMaxMessages = 200;
    private long attachmentMaxBytes = 500L * 1024 * 1024;
    private long uploadWarningBytes = 10L * 1024 * 1024 * 1024;
    private String trashDir;

    @Data
    public static class Ai {
        private String provider = "siliconflow";
        private String baseUrl = "https://api.siliconflow.cn/v1";
        private String model = "Qwen/Qwen3.8-27B";
        private String apiKey = "";
        private int timeoutSeconds = 120;
        private double temperature = 0.3;
        private Integer maxTokens;
        private Integer visionMaxTokens;
        private Integer generationMaxTokens;
        private Integer chatMaxTokens;
        private Integer assistantMaxTokens;
    }

    public java.nio.file.Path recycleRoot() {
        if (trashDir != null && !trashDir.isBlank()) return java.nio.file.Path.of(trashDir).toAbsolutePath().normalize();
        return java.nio.file.Path.of(System.getProperty("user.home"), "Desktop", "智能体回收站", "垃圾桶", "AIcademiya").toAbsolutePath().normalize();
    }
    public int answerPageLimit() { return Math.max(1, Math.min(50, historyMaxAnswers)); }
    public int conversationPageLimit() { return Math.max(1, Math.min(10, historyMaxConversations)); }
    public int conversationMessageLimit() { return Math.max(4, Math.min(2000, historyMaxMessages)); }
}
