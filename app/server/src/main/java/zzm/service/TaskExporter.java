package zzm.service;

import zzm.dto.TaskContent;
import cn.hutool.json.JSONUtil;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;
import java.nio.charset.StandardCharsets;
import java.util.*;
import static zzm.exception.ApiErrors.error;

/** Markdown serialization of an authorized task snapshot; no document rendering or model calls. */
@Component
public class TaskExporter {
    public byte[] exportResult(Map<String, Object> task, cn.hutool.json.JSONObject answers,
        cn.hutool.json.JSONArray messages, String teacherNote, List<Map<String, Object>> attachments, String base) {
        boolean chinese = "zh-CN".equals(task.get("teachingLanguage"));
        StringBuilder out = new StringBuilder(lesson(task, base));
        TaskContent content = JSONUtil.parseObj(task.get("content")).toBean(TaskContent.class);
        heading(out, 2, chinese ? "我的作答" : "My answers");
        for (int index = 0; index < content.getQuestions().size(); index++) {
            var question = content.getQuestions().get(index);
            heading(out, 3, chinese ? "第 " + (index + 1) + " 题" : "Question " + (index + 1));
            markdown(out, question.getPrompt());
            markdown(out, answers.getStr(question.getId(), chinese ? "尚未作答" : "No answer yet"));
        }
        section(out, chinese ? "教师反馈" : "Teacher feedback", teacherNote);
        heading(out, 2, chinese ? "本次对话" : "Current conversation");
        for (Object item : messages) {
            var message = JSONUtil.parseObj(item);
            if (message.getBool("pendingReview", false)) {
                markdown(out, chinese ? "AI 反馈等待教师审核。" : "AI feedback is awaiting teacher review.");
                continue;
            }
            heading(out, 3, "user".equals(message.getStr("role"))
                ? (chinese ? "学生" : "Student") : (chinese ? "AI 辅导教师" : "AI tutor"));
            markdown(out, message.getStr("content", ""));
        }
        if (!attachments.isEmpty()) {
            heading(out, 2, chinese ? "我的附件" : "My attachments");
            Map<String, String> titles = new LinkedHashMap<>();
            attachments.forEach(file -> titles.put(Objects.toString(file.get("id")), Objects.toString(file.get("title"))));
            titles.keySet().forEach(id -> resource(out, id, titles, base, "", false));
        }
        return out.toString().getBytes(StandardCharsets.UTF_8);
    }
    private String lesson(Map<String, Object> snapshot, String materialBaseUrl) {
        TaskContent content = JSONUtil.parseObj(snapshot.get("content")).toBean(TaskContent.class);
        boolean chinese = "zh-CN".equals(snapshot.get("teachingLanguage"));
        Map<String, String> materialTitles = new LinkedHashMap<>();
        var materials = JSONUtil.parseObj(snapshot).getJSONArray("materials");
        if (materials != null) materials.forEach(item -> {
            var material = JSONUtil.parseObj(item);
            materialTitles.put(material.getStr("id"), material.getStr("title", material.getStr("fileName", "Material")));
        });
        String versionId = Objects.toString(snapshot.get("versionId"), "");
        StringBuilder out = new StringBuilder();
        heading(out, 1, Objects.toString(snapshot.get("title"), chinese ? "学习任务" : "Learning task"));
        markdown(out, Objects.toString(snapshot.get("description"), ""));
        section(out, chinese ? "开场白" : "Welcome", content.getOpeningMessage());

        if (!content.getLearningGoals().isEmpty()) {
            heading(out, 2, chinese ? "学习目标" : "Learning goals");
            content.getLearningGoals().forEach(goal -> markdown(out, "- " + goal.replace("\n", "\n  ")));
        }
        if (!content.getLearningPlan().isEmpty()) {
            heading(out, 2, chinese ? "学习计划" : "Learning plan");
            for (var step : content.getLearningPlan()) {
                heading(out, 3, step.getTitle());
                if (step.getDurationMinutes() != null)
                    markdown(out, step.getDurationMinutes() + (chinese ? " 分钟" : " minutes"));
                markdown(out, step.getDescription());
            }
        }
        section(out, chinese ? "讲义" : "Lesson notes", content.getHandout());
        for (String id : content.getIllustrationMaterialIds())
            resource(out, id, materialTitles, materialBaseUrl, versionId, true);

        if (!content.getDiagrams().isEmpty()) {
            heading(out, 2, chinese ? "结构图" : "Diagrams");
            for (var diagram : content.getDiagrams()) {
                heading(out, 3, diagram.getTitle());
                Map<String, String> nodes = new LinkedHashMap<>();
                for (var node : diagram.getNodes()) {
                    nodes.put(node.getId(), node.getText());
                    markdown(out, "- " + label(node.getText()));
                }
                if (!diagram.getEdges().isEmpty()) {
                    heading(out, 4, chinese ? "节点关系" : "Relationships");
                    for (var edge : diagram.getEdges()) {
                        String relation = "- " + label(nodes.getOrDefault(edge.getFrom(), edge.getFrom()))
                            + " → " + label(nodes.getOrDefault(edge.getTo(), edge.getTo()));
                        if (edge.getLabel() != null && !edge.getLabel().isBlank()) relation += " — " + label(edge.getLabel());
                        markdown(out, relation);
                    }
                }
            }
        }
        if (!content.getQuestions().isEmpty()) {
            heading(out, 2, chinese ? "题目" : "Questions");
            for (int i = 0; i < content.getQuestions().size(); i++) {
                var question = content.getQuestions().get(i);
                heading(out, 3, chinese ? "第 " + (i + 1) + " 题" : "Question " + (i + 1));
                markdown(out, question.getPrompt());
                for (String id : question.getImageMaterialIds())
                    resource(out, id, materialTitles, materialBaseUrl, versionId, true);
                for (String option : question.getOptions()) markdown(out, "- [ ] " + option.replace("\n", "\n  "));
                if (question.getHint() != null && !question.getHint().isBlank()) {
                    heading(out, 4, chinese ? "提示" : "Hint");
                    markdown(out, question.getHint());
                }
            }
        }
        if (!materialTitles.isEmpty()) {
            heading(out, 2, chinese ? "学习材料" : "Materials");
            markdown(out, chinese ? "材料链接需要登录本平台并具备相应权限；文件未嵌入此 Markdown。"
                : "Material links require access to this platform; files are not embedded in this Markdown document.");
            for (String id : materialTitles.keySet())
                resource(out, id, materialTitles, materialBaseUrl, versionId, false);
        }
        return out.toString();
    }

    private void resource(StringBuilder out, String id, Map<String, String> titles, String base, String versionId, boolean image) {
        if (!titles.containsKey(id)) throw error(422, "Some resource references are unavailable in this export.");
        var uri = UriComponentsBuilder.fromUriString(base).pathSegment(id, "file");
        if (!versionId.isBlank()) uri.queryParam("versionId", versionId);
        markdown(out, (image ? "![" : "- [") + label(titles.get(id)) + "](" + uri.build().encode().toUriString() + ")");
    }
    private void section(StringBuilder out, String title, String text) {
        if (text == null || text.isBlank()) return;
        heading(out, 2, title);
        markdown(out, text);
    }
    private void subsection(StringBuilder out, String title, String text) {
        if (text == null || text.isBlank()) return;
        heading(out, 4, title);
        markdown(out, text);
    }
    private void heading(StringBuilder out, int level, String text) {
        markdown(out, "#".repeat(level) + " " + label(text));
    }
    private String label(String text) {
        return Objects.toString(text, "").replace("\\", "\\\\").replace("\r", " ").replace("\n", " ")
            .replace("[", "\\[").replace("]", "\\]").replace("*", "\\*").replace("_", "\\_")
            .replace("<", "&lt;").replace(">", "&gt;");
    }
    private void markdown(StringBuilder out, String text) {
        if (text == null || text.isBlank()) return;
        // Keep Markdown source intact, including indentation, fenced code, tables and math delimiters.
        out.append(text);
        if (!text.endsWith("\n")) out.append('\n');
        out.append('\n');
    }
}
