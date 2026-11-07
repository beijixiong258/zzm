package zzm.service.impl;

import cn.hutool.core.util.IdUtil;
import cn.hutool.json.JSONUtil;
import com.baomidou.mybatisplus.extension.conditions.query.LambdaQueryChainWrapper;
import com.baomidou.mybatisplus.extension.conditions.update.LambdaUpdateChainWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import zzm.dto.FormativeAssessment;
import zzm.dto.RetrievalContent;
import zzm.dto.TaskContent;
import zzm.entity.CourseMaterial;
import zzm.entity.LearningAssessment;
import zzm.entity.LearningRecord;
import zzm.mapper.LearningAssessmentMapper;
import zzm.service.AiService;
import zzm.service.LearningAssessmentService;
import zzm.service.MaterialService;
import zzm.service.PdfInputReader;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.*;
import static zzm.exception.ApiErrors.error;

@Slf4j
@Service
@RequiredArgsConstructor
public class LearningAssessmentServiceImpl extends ServiceImpl<LearningAssessmentMapper, LearningAssessment> implements LearningAssessmentService {
    private static final int MAX_SOURCE_CHARS = 12000;
    private static final int PAGE_SIZE = 20;
    private final AiService ai;
    private final MaterialService materials;
    private final PdfInputReader pdf;
    private final ObjectMapper json;

    @Override public void enqueue(LearningRecord record, String courseId, String language, TaskContent content,
        Map<String, Object> answers, List<CourseMaterial> attachments) {
        LearningAssessment assessment = new LearningAssessment();
        assessment.setRecordId(record.getId());
        assessment.setSubmissionRevision(record.getRevision());
        assessment.setSubmittedAt(record.getSubmittedAt());
        assessment.setUpdatedAt(record.getSubmittedAt());
        assessment.setQuestionCount(content.getQuestions().size());
        assessment.setEvaluatedCount(0);
        boolean hasQuestions = !content.getQuestions().isEmpty();
        assessment.setStatus(hasQuestions ? "queued" : "noQuestions");
        assessment.setInputJson(hasQuestions
            ? RetrievalContent.json(freeze(courseId, language, content, answers, attachments)) : "{}");
        if (!save(assessment)) throw error(409, "The assessment could not be queued. Submit again.");
    }

    private FormativeAssessment.Submission freeze(String courseId, String language, TaskContent content,
        Map<String, Object> answers, List<CourseMaterial> attachments) {
        Set<String> referenceIds = new LinkedHashSet<>();
        Map<String, List<CourseMaterial>> filesByQuestion = new HashMap<>();
        for (CourseMaterial file : attachments)
            filesByQuestion.computeIfAbsent(file.getQuestionId(), ignored -> new ArrayList<>()).add(file);
        for (TaskContent.Question question : content.getQuestions()) {
            referenceIds.addAll(Objects.requireNonNullElse(question.getSourceMaterialIds(), List.of()));
            referenceIds.addAll(Objects.requireNonNullElse(question.getImageMaterialIds(), List.of()));
        }
        Map<String, CourseMaterial> references = new HashMap<>();
        if (!referenceIds.isEmpty()) materials.listByIds(referenceIds).forEach(file -> {
            if (courseId.equals(file.getCourseId()) && file.getOwnerId() == null && file.getFileRemovedAt() == null)
                references.put(file.getId(), file);
        });
        Map<String, String> aliases = new HashMap<>();
        Map<String, FormativeAssessment.Source> sources = new LinkedHashMap<>();
        List<FormativeAssessment.Question> questions = new ArrayList<>();
        for (TaskContent.Question question : content.getQuestions()) {
            List<String> studentSources = filesByQuestion.getOrDefault(question.getId(), List.of()).stream()
                .map(file -> snapshotSource(file, aliases, sources)).toList();
            Set<String> linked = new LinkedHashSet<>(Objects.requireNonNullElse(question.getImageMaterialIds(), List.of()));
            linked.addAll(Objects.requireNonNullElse(question.getSourceMaterialIds(), List.of()));
            List<String> referenceSources = new ArrayList<>();
            for (String id : linked) {
                CourseMaterial source = references.get(id);
                if (source != null) referenceSources.add(snapshotSource(source, aliases, sources));
            }
            String answer = Objects.toString(answers.get(question.getId()), "");
            if ("multipleChoice".equals(question.getType()))
                answer = String.join("\n", TaskContent.multipleChoiceAnswers(answer, question.getOptions()));
            questions.add(new FormativeAssessment.Question(questions.size() + 1, question.getId(), question.getType(),
                question.getPrompt(), question.getOptions(), question.getAnswerSlots(), question.getReferenceAnswer(),
                question.getExplanation(), answer, studentSources, referenceSources));
        }
        return new FormativeAssessment.Submission(language, content.getLearningGoals(), content.getRubric(), questions, sources);
    }

    private String snapshotSource(CourseMaterial file, Map<String, String> aliases, Map<String, FormativeAssessment.Source> sources) {
        return aliases.computeIfAbsent(file.getId(), id -> {
            String mime = Objects.toString(file.getMimeType(), "");
            int visualPages = mime.startsWith("image/") ? 1 : 0;
            String text = Objects.toString(file.getTextContent(), "");
            if (PdfInputReader.isPdf(file)) {
                var report = pdf.report(file);
                if ("images".equals(report.getPdfInputMode()) && pdf.complete(report)) {
                    visualPages = report.getUnitsTotal();
                    // 图像模式的占位说明不算作学生作答。
                    text = "";
                }
            }
            boolean limited = text.length() > MAX_SOURCE_CHARS;
            if (limited) {
                int end = MAX_SOURCE_CHARS;
                if (Character.isHighSurrogate(text.charAt(end - 1))) end--;
                text = text.substring(0, end);
            }
            String alias = "source" + (sources.size() + 1);
            sources.put(alias, new FormativeAssessment.Source(id, file.getTitle(), text,
                visualPages > 0 ? RetrievalContent.materialKey(file) : null, visualPages, limited));
            return alias;
        });
    }

    private LambdaQueryChainWrapper<LearningAssessment> summaries() {
        return lambdaQuery().select(LearningAssessment::getId, LearningAssessment::getRecordId,
            LearningAssessment::getSubmissionRevision, LearningAssessment::getStatus, LearningAssessment::getQuestionCount,
            LearningAssessment::getEvaluatedCount, LearningAssessment::getSubmittedAt, LearningAssessment::getEvaluatedAt,
            LearningAssessment::getTeacherScore, LearningAssessment::getScoredAt);
    }

    @Override public Map<String, Object> latest(String recordId) {
        LearningAssessment row = summaries().eq(LearningAssessment::getRecordId, recordId)
            .orderByDesc(LearningAssessment::getSubmissionRevision).last("LIMIT 1").one();
        return row == null ? null : summary(row);
    }

    @Override public Map<String, Map<String, Object>> latestForRecords(Collection<String> recordIds) {
        if (recordIds.isEmpty()) return Map.of();
        Map<String, Map<String, Object>> result = new HashMap<>();
        summaries().in(LearningAssessment::getRecordId, recordIds).orderByDesc(LearningAssessment::getSubmissionRevision)
            .list().forEach(row -> result.computeIfAbsent(row.getRecordId(), ignored -> summary(row)));
        return result;
    }

    @Override public Map<String, Object> history(String recordId, int page) {
        if (page < 1 || page > 1000000) throw error(422, "Invalid history page");
        var rows = summaries().eq(LearningAssessment::getRecordId, recordId)
            .orderByDesc(LearningAssessment::getSubmissionRevision).page(new Page<>(page, PAGE_SIZE));
        return Map.of("items", rows.getRecords().stream().map(this::summary).toList(),
            "page", page, "hasMore", rows.hasNext());
    }

    private Map<String, Object> summary(LearningAssessment row) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", row.getId());
        result.put("submissionRevision", row.getSubmissionRevision());
        result.put("status", row.getStatus());
        result.put("questionCount", row.getQuestionCount());
        result.put("evaluatedCount", row.getEvaluatedCount());
        result.put("submittedAt", row.getSubmittedAt());
        result.put("evaluatedAt", row.getEvaluatedAt());
        result.put("teacherScore", row.getTeacherScore());
        result.put("scoredAt", row.getScoredAt());
        return result;
    }

    @Override public Map<String, Object> detail(String recordId, String id) {
        LearningAssessment row = lambdaQuery().select(LearningAssessment.class, field -> !Set.of("inputJson", "runId").contains(field.getProperty()))
            .eq(LearningAssessment::getRecordId, recordId).eq(LearningAssessment::getId, id).one();
        if (row == null) throw error(404, "Assessment not found.");
        Map<String, Object> result = summary(row);
        result.put("feedback", row.getFeedbackJson() == null ? null : JSONUtil.parseObj(row.getFeedbackJson()));
        return result;
    }

    @Override public Map<String, Object> retry(String recordId, String id) {
        if (!forRecord(recordId, id).eq(LearningAssessment::getStatus, "failed")
            .set(LearningAssessment::getStatus, "queued").set(LearningAssessment::getEvaluatedCount, 0)
            .set(LearningAssessment::getRunId, null).set(LearningAssessment::getUpdatedAt, now()).update())
            throw error(409, "Only a failed assessment can be retried.");
        return detail(recordId, id);
    }

    @Override public Map<String, Object> saveScore(String recordId, String id, BigDecimal score) {
        if (score != null && (score.signum() < 0 || score.compareTo(BigDecimal.valueOf(100)) > 0 || score.stripTrailingZeros().scale() > 2))
            throw error(422, "Enter a score between 0 and 100 with up to two decimal places.");
        if (!forRecord(recordId, id).set(LearningAssessment::getTeacherScore, score)
            .set(LearningAssessment::getScoredAt, score == null ? null : now()).update())
            throw error(404, "Assessment not found.");
        return detail(recordId, id);
    }

    private LambdaUpdateChainWrapper<LearningAssessment> forRecord(String recordId, String id) {
        return lambdaUpdate().eq(LearningAssessment::getRecordId, recordId).eq(LearningAssessment::getId, id);
    }

    @Override public void recoverProcessing() {
        lambdaUpdate().eq(LearningAssessment::getStatus, "running").set(LearningAssessment::getStatus, "failed")
            .set(LearningAssessment::getRunId, null).set(LearningAssessment::getUpdatedAt, now()).update();
    }

    @Override public void processNext() {
        LearningAssessment row = lambdaQuery().eq(LearningAssessment::getStatus, "queued")
            .orderByAsc(LearningAssessment::getSubmittedAt, LearningAssessment::getId).last("LIMIT 1").one();
        if (row == null) return;
        String run = IdUtil.fastSimpleUUID();
        if (!forRecord(row.getRecordId(), row.getId()).eq(LearningAssessment::getStatus, "queued")
            .set(LearningAssessment::getStatus, "running").set(LearningAssessment::getRunId, run)
            .set(LearningAssessment::getUpdatedAt, now()).update()) return;
        try {
            var submission = json.readValue(row.getInputJson(), FormativeAssessment.Submission.class);
            List<FormativeAssessment.QuestionFeedback> results = new ArrayList<>();
            for (List<FormativeAssessment.Question> batch : batches(submission)) {
                if (!stillRunning(row, run)) return;
                Map<String, CourseMaterial> visualFiles = visualFiles(submission, batch);
                results.addAll(ai.assessAnswers(submission, batch, visualFiles));
                if (!running(row, run).set(LearningAssessment::getEvaluatedCount, results.size())
                    .set(LearningAssessment::getUpdatedAt, now()).update()) return;
            }
            if (results.size() != row.getQuestionCount()) throw new IllegalStateException("评价题数与提交不符");
            LocalDateTime completed = now();
            running(row, run).set(LearningAssessment::getStatus, "completed").set(LearningAssessment::getRunId, null)
                .set(LearningAssessment::getFeedbackJson, RetrievalContent.json(summarise(results)))
                .set(LearningAssessment::getUpdatedAt, completed).set(LearningAssessment::getEvaluatedAt, completed).update();
        } catch (Exception exception) {
            log.warn("形成性评价失败，评价编号={}，异常类型={}", row.getId(), exception.getClass().getSimpleName());
            running(row, run).set(LearningAssessment::getStatus, "failed").set(LearningAssessment::getRunId, null)
                .set(LearningAssessment::getUpdatedAt, now()).update();
        }
    }

    private boolean stillRunning(LearningAssessment row, String run) {
        return lambdaQuery().eq(LearningAssessment::getId, row.getId()).eq(LearningAssessment::getStatus, "running")
            .eq(LearningAssessment::getRunId, run).count() > 0;
    }

    private LambdaUpdateChainWrapper<LearningAssessment> running(LearningAssessment row, String run) {
        return forRecord(row.getRecordId(), row.getId()).eq(LearningAssessment::getStatus, "running").eq(LearningAssessment::getRunId, run);
    }

    private List<List<FormativeAssessment.Question>> batches(FormativeAssessment.Submission submission) {
        List<List<FormativeAssessment.Question>> result = new ArrayList<>();
        List<FormativeAssessment.Question> batch = new ArrayList<>();
        int characters = 0;
        for (var question : submission.questions()) {
            List<FormativeAssessment.Source> sources = sourcesFor(submission, question);
            boolean visual = sources.stream().anyMatch(source -> source.visualPages() > 0);
            int size = RetrievalContent.json(question).length() + sources.stream().mapToInt(source -> source.text().length()).sum();
            if (!batch.isEmpty() && (visual || batch.size() >= 6 || characters + size > 24000)) {
                result.add(batch);
                batch = new ArrayList<>();
                characters = 0;
            }
            if (visual) result.add(List.of(question));
            else {
                batch.add(question);
                characters += size;
            }
        }
        if (!batch.isEmpty()) result.add(batch);
        return result;
    }

    private Map<String, CourseMaterial> visualFiles(FormativeAssessment.Submission submission, List<FormativeAssessment.Question> batch) {
        Set<String> ids = new LinkedHashSet<>();
        for (var question : batch) sourcesFor(submission, question).stream().filter(source -> source.visualPages() > 0)
            .forEach(source -> ids.add(source.materialId()));
        Map<String, CourseMaterial> files = new HashMap<>();
        if (!ids.isEmpty()) materials.listByIds(ids).forEach(file -> files.put(file.getId(), file));
        return files;
    }

    private List<FormativeAssessment.Source> sourcesFor(FormativeAssessment.Submission submission, FormativeAssessment.Question question) {
        List<String> ids = new ArrayList<>(question.studentSources());
        ids.addAll(question.referenceSources());
        return ids.stream().distinct().map(submission.sources()::get).toList();
    }

    private FormativeAssessment.Feedback summarise(List<FormativeAssessment.QuestionFeedback> results) {
        List<FormativeAssessment.QuestionFeedback> priority = results.stream()
            .sorted(Comparator.comparingInt(item -> switch (item.judgement()) {
                case "revise" -> 0;
                case "partial", "insufficient" -> 1;
                default -> 2;
            })).toList();
        return new FormativeAssessment.Feedback(
            results.stream().filter(item -> !item.strength().isBlank()).limit(3)
                .map(item -> new FormativeAssessment.Point(item.number(), item.strength())).toList(),
            priority.stream().filter(item -> !item.improvement().isBlank()).limit(3)
                .map(item -> new FormativeAssessment.Point(item.number(), item.improvement())).toList(),
            priority.stream().limit(3).map(item -> new FormativeAssessment.Point(item.number(), item.nextStep())).toList(),
            results);
    }

    private static LocalDateTime now() {
        return LocalDateTime.now(ZoneOffset.UTC);
    }
}
