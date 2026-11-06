package zzm.dto;

import cn.hutool.json.JSONUtil;
import lombok.Data;
import zzm.entity.CourseMaterial;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

/** 可重建的检索表示；片段标识只在同一内容指纹下有效。 */
@Data
public class RetrievalContent {
    private static final com.fasterxml.jackson.databind.ObjectMapper JSON = new com.fasterxml.jackson.databind.ObjectMapper().findAndRegisterModules();
    private String sourceKey = "";
    private String revision = "";
    private int nextPage = 1;
    private boolean complete;
    private long visionInputTokens;
    private List<Part> parts = new ArrayList<>();

    public record Part(String id, String text, int page, String method, boolean reliable) {}
    public record Scope(String id, String revision) {}
    public record Corpus(String id, String revision, String title, List<Part> parts) {}
    public record Hit(String corpusId, String revision, String partId, int page, String snippet, double score) {}

    public static String json(Object value) {
        try { return JSON.writeValueAsString(value); }
        catch (com.fasterxml.jackson.core.JsonProcessingException exception) { throw new IllegalArgumentException(exception); }
    }

    public static String hash(String text) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8))); }
        catch (java.security.NoSuchAlgorithmException exception) { throw new IllegalStateException(exception); }
    }
    public static String materialKey(CourseMaterial material) {
        return hash("retrieval-1\n" + material.getId() + "\n" + material.getStoragePath() + "\n"
            + Objects.toString(material.getTextContent(), "") + "\n" + Objects.toString(material.getExtractionReportJson(), ""));
    }
    public static String sourceKey(CourseMaterial material) {
        String key = materialKey(material);
        return material.hasPdfFormat() ? hash("pdf-visual-2\n" + key) : key;
    }
    public static RetrievalContent read(CourseMaterial material) {
        RetrievalContent result;
        try { result = material.getRetrievalJson() == null ? new RetrievalContent()
            : JSON.readValue(material.getRetrievalJson(), RetrievalContent.class); }
        catch (com.fasterxml.jackson.core.JsonProcessingException exception) { result = new RetrievalContent(); }
        String key = sourceKey(material);
        if (!key.equals(result.sourceKey)) {
            result = new RetrievalContent(); result.sourceKey = key;
        }
        return result;
    }
    public void finish() {
        complete = true;
        revision = hash(sourceKey + json(parts));
    }
    public void appendPdfPage(int page, String nativeText, DocumentExtraction.VisualReading reading) {
        append(nativeText, page, "native", true);
        if (reading == null) return;
        if (nativeText.isBlank()) append(reading.getText(), page, "vision", reading.isReadable());
        for (String passage : reading.getVisualPassages()) append(passage, page, "vision", reading.isReadable());
        visionInputTokens += reading.getInputTokens();
    }

    /** 优先保留完整段落；过长段落明确拆成可连续读取的片段，不改写原文。 */
    public void append(String text, int page, String method, boolean reliable) {
        StringBuilder current = new StringBuilder();
        for (String paragraph : Objects.toString(text, "").split("(?<=\n)")) {
            if (current.length() + paragraph.length() > 2400 && !current.isEmpty()) {
                part(current.toString(), page, method, reliable); current.setLength(0);
            }
            for (int start = 0; start < paragraph.length();) {
                int end = Math.min(paragraph.length(), start + 2400);
                if (end < paragraph.length() && Character.isHighSurrogate(paragraph.charAt(end - 1))) end--;
                if (start > 0 || current.length() + end - start > 2400) {
                    part(current.toString(), page, method, reliable); current.setLength(0);
                }
                current.append(paragraph, start, end); start = end;
            }
        }
        part(current.toString(), page, method, reliable);
    }
    private void part(String text, int page, String method, boolean reliable) {
        if (!text.isBlank()) parts.add(new Part("s" + parts.size(), text, page, method, reliable));
    }
    public static Corpus lesson(String id, String text) {
        RetrievalContent content = new RetrievalContent(); content.sourceKey = hash(text);
        content.append(text, 0, "published", true); content.finish();
        return new Corpus(id, content.revision, "Current lesson", content.parts);
    }
    public static String lessonText(cn.hutool.json.JSONObject snapshot) {
        var content = snapshot.getJSONObject("content");
        return content.getStr("handout", "") + "\n" + Objects.toString(content.get("diagrams"), "");
    }
}
