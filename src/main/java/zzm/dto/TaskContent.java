package zzm.dto;

import cn.hutool.json.*;
import lombok.Data;
import java.util.ArrayList;
import java.util.List;

@Data
public class TaskContent {
    private String description = "";
    private List<String> learningGoals = new ArrayList<>();
    private List<LearningStep> learningPlan = new ArrayList<>();
    private String openingMessage = "";
    private String handout = "";
    private String teachingMode = "guided";
    private String feedbackMode = "immediate";
    private String rubric = "";
    private List<String> illustrationMaterialIds = new ArrayList<>();
    private List<Diagram> diagrams = new ArrayList<>();
    private List<Question> questions = new ArrayList<>();
    private AiConfig aiConfig = new AiConfig();

    public static List<String> multipleChoiceAnswers(String answer, List<String> options) {
        if (answer == null || answer.isBlank()) return List.of();
        if (answer.strip().startsWith("[")) {
            try {
                JSONArray values = JSONUtil.parseArray(answer);
                if (values.stream().allMatch(value -> value instanceof String && (options == null || options.isEmpty() || options.contains(value))))
                    return values.toList(String.class);
            } catch (JSONException ignored) { /* Existing records use newline-separated option text. */ }
        }
        if (options != null && options.contains(answer)) return List.of(answer);
        return answer.lines().filter(value -> !value.isEmpty()).toList();
    }

    @Data public static class Diagram {
        private String id;
        private String title;
        private List<DiagramNode> nodes = new ArrayList<>();
        private List<DiagramEdge> edges = new ArrayList<>();
    }
    @Data public static class DiagramNode {
        private String id;
        private String text;
        private Integer x = 0;
        private Integer y = 0;
    }
    @Data public static class DiagramEdge {
        private String from;
        private String to;
        private String label = "";
    }
    @Data public static class LearningStep {
        private String title;
        private String description;
        private Integer durationMinutes;
    }
    @Data public static class Question {
        private String id;
        private String type;
        private String prompt;
        private List<String> options = new ArrayList<>();
        public void setOptions(List<String> options) {
            this.options = options == null ? new ArrayList<>() : options;
        }
        private Integer answerSlots = 1;
        private String referenceAnswer;
        private String explanation;
        private String hint;
        private List<String> sourceMaterialIds = new ArrayList<>();
        private List<String> imageMaterialIds = new ArrayList<>();
    }
    @Data public static class AiConfig {
        private String teachingApproach;
        private String feedbackStrategy;
        private String responseDetail;
        private String tone;
    }
}
