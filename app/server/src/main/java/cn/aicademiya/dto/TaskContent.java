package cn.aicademiya.dto;

import lombok.Data;
import java.util.ArrayList;
import java.util.List;

@Data
public class TaskContent {
    private String description = "";
    private List<String> learningGoals = new ArrayList<>();
    private List<LearningStep> learningPlan = new ArrayList<>();
    private String openingMessage = "";
    private List<Question> questions = new ArrayList<>();
    private AiConfig aiConfig = new AiConfig();

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
