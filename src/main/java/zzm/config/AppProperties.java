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
    private Tutor tutor = new Tutor();
    private Retrieval retrieval = new Retrieval();
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
    public static class Tutor {
        private int inputTarget = 12000;
        private int materialTokens = 4000;
        private int recentTokens = 3000;
        private int recentMessages = 16;
        private int summaryTokens = 1000;
        private int inputLimit = 200000;
        private int contextWindow = 256000;
        private int turnInputLimit = 60000;
        private int toolRounds = 3;
        private int toolCalls = 8;
        private int timeoutSeconds = 120;
    }

    @Data
    public static class Retrieval {
        private boolean enabled = true;
        private String baseUrl = "http://retrieval:8181";
        private int timeoutSeconds = 12;
        private boolean rerank = false;
    }

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
    public java.nio.file.Path uploadRoot() {
        return java.nio.file.Path.of(uploadDir).toAbsolutePath().normalize();
    }
    public java.nio.file.Path uploadPath(String storedPath) { return resolveStoredPath(uploadRoot(), storedPath); }
    public java.nio.file.Path recycledPath(String storedPath) { return resolveStoredPath(recycleRoot(), storedPath); }
    private java.nio.file.Path resolveStoredPath(java.nio.file.Path root, String storedPath) {
        if (storedPath == null || storedPath.isBlank()) throw new IllegalArgumentException("Stored file path is missing");
        java.nio.file.Path relative = java.nio.file.Path.of(storedPath.replace('\\', '/'));
        java.nio.file.Path resolved = root.resolve(relative).normalize();
        if (relative.isAbsolute() || storedPath.matches("^[A-Za-z]:.*") || resolved.equals(root) || !resolved.startsWith(root))
            throw new IllegalArgumentException("Stored file path must be relative to its storage directory");
        return resolved;
    }
    public int answerPageLimit() { return Math.max(1, Math.min(50, historyMaxAnswers)); }
    public int conversationPageLimit() { return Math.max(1, Math.min(10, historyMaxConversations)); }
    public int conversationMessageLimit() { return Math.max(4, Math.min(2000, historyMaxMessages)); }
}
