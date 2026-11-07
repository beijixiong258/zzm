package zzm.dto;

import java.util.List;
import java.util.Map;

/** 每次提交冻结题目和证据，公开结果只包含评价所需的投影。 */
public final class FormativeAssessment {
    private FormativeAssessment() {}

    public record Submission(String language, List<String> goals, String rubric,
        List<Question> questions, Map<String, Source> sources) {}

    public record Question(int number, String id, String type, String prompt, List<String> options,
        Integer answerSlots, String referenceAnswer, String explanation, String answer,
        List<String> studentSources, List<String> referenceSources) {}

    public record Source(String materialId, String title, String text, String visualKey,
        int visualPages, boolean limited) {}

    public record ModelResult(List<ModelQuestion> questions) {}

    public record ModelQuestion(Integer number, String judgement, String evidenceId, String quote,
        String strength, String improvement, String nextStep) {}

    public record QuestionFeedback(int number, String questionId, String prompt, String judgement, String evidenceLabel,
        String quote, String strength, String improvement, String nextStep) {}

    public record Point(int questionNumber, String text) {}

    public record Feedback(List<Point> strengths, List<Point> improvements, List<Point> nextSteps,
        List<QuestionFeedback> questions) {}
}
