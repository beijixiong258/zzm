package zzm.service.impl;

import zzm.dto.*;
import zzm.entity.*;
import zzm.mapper.GenerationJobMapper;
import zzm.service.*;
import cn.hutool.json.*;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import java.time.*;
import java.util.*;
import static zzm.exception.ApiErrors.error;

@Service
@RequiredArgsConstructor
public class GenerationServiceImpl extends ServiceImpl<GenerationJobMapper, GenerationJob> implements GenerationService {
    private final SessionService sessions;
    private final CourseService courses;
    private final MaterialService materials;
    private final AccountService accounts;
    private final AiService ai;

    @Override public List<Map<String, Object>> listJobs(String sessionId, AccountUser user) {
        sessions.require(sessionId, user, true);
        return lambdaQuery().eq(GenerationJob::getSessionId, sessionId)
            .orderByDesc(GenerationJob::getCreatedAt).list().stream().map(this::view).toList();
    }

    @Override public Map<String, Object> assistTeacher(Requests.TeacherChat input, AccountUser user) {
        accounts.requireStaff(user);
        Map<String, Object> context = new LinkedHashMap<>();
        context.put("scope", input.getScope()); context.put("locale", input.getLocale());
        if (input.getCourseId() != null && !input.getCourseId().isBlank())
            context.put("course", courses.view(courses.requireAccess(input.getCourseId(), user, true), user));
        if (input.getTaskId() != null && !input.getTaskId().isBlank()) {
            TeachingSession task = sessions.require(input.getTaskId(), user, true);
            if (!task.getCourseId().equals(input.getCourseId())) throw error(403, "Task does not belong to the current course");
        }
        context.put("courseDraft", input.getCourseDraft()); context.put("taskDraft", input.getTaskDraft());
        return ai.configureTeacher(input, context);
    }

    @Override @Transactional public GenerationJob start(String sessionId, Requests.Generation input, AccountUser user) {
        TeachingSession session = sessions.require(sessionId, user, true);
        if (!session.getRevision().equals(input.getRevision())) throw error(409, "Save or reload the latest task before generating");
        if (lambdaQuery().eq(GenerationJob::getSessionId, sessionId).in(GenerationJob::getStatus, "queued", "running").count() > 0) throw error(409, "Generation is already running");
        List<String> ids = JSONUtil.toList(session.getMaterialIdsJson(), String.class);
        List<CourseMaterial> selected = materials.selected(session.getCourseId(), ids);
        if ("import".equals(input.getKind()) && selected.isEmpty()) throw error(422, "Select processed materials with readable content");
        if ("revise".equals(input.getKind()) && Objects.toString(input.getInstruction(), "").isBlank()) throw error(422, "Describe the revision you want");
        materials.requireProcessed(selected);
        if (input.getSourceMaterialIds().isEmpty() && input.getSourceMaterialId() != null) input.setSourceMaterialIds(List.of(input.getSourceMaterialId()));
        if ("import".equals(input.getKind()) && (input.getSourceMaterialIds().isEmpty() || !ids.containsAll(input.getSourceMaterialIds()))) throw error(422, "Choose one or more selected materials to extract questions from");
        if (!sessions.updateById(session)) throw error(409, "Task changed. Reload before generating.");
        GenerationJob job = new GenerationJob(); job.setSessionId(sessionId); job.setOwnerId(user.getId()); job.setKind(input.getKind());
        job.setExpectedRevision(session.getRevision()); job.setStatus("queued"); job.setStage("queued");
        job.setRequestJson(JSONUtil.toJsonStr(input)); job.setErrorMessage(""); job.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC)); job.setUpdatedAt(job.getCreatedAt());
        save(job); return job;
    }
    @Override public GenerationJob require(String id, AccountUser user) {
        GenerationJob job = getById(id); if (job == null) throw error(404, "Generation job not found");
        sessions.require(job.getSessionId(), user, true); return job;
    }
    @Override @Transactional public TeachingSession apply(String id, AccountUser user) {
        GenerationJob job = require(id, user);
        TeachingSession session = sessions.require(job.getSessionId(), user, true);
        if ("applied".equals(job.getStatus())) return session;
        if (!"succeeded".equals(job.getStatus())) throw error(409, "Generation is not ready to apply");
        if (!session.getRevision().equals(job.getExpectedRevision())) throw error(409, "Task was edited during generation. The generated result has been retained; reload and generate again.");
        TaskContent generated = JSONUtil.toBean(job.getResultJson(), TaskContent.class);
        if ("import".equals(job.getKind())) {
            TaskContent current = JSONUtil.toBean(session.getContentJson(), TaskContent.class);
            Set<String> existingIds = new HashSet<>(); current.getQuestions().forEach(q -> existingIds.add(q.getId()));
            generated.getQuestions().forEach(q -> { if (existingIds.contains(q.getId())) q.setId(cn.hutool.core.util.IdUtil.fastSimpleUUID()); });
            current.getQuestions().addAll(generated.getQuestions());
            if (current.getLearningGoals().isEmpty()) current.setLearningGoals(generated.getLearningGoals());
            if (current.getHandout().isBlank()) current.setHandout(generated.getHandout()); if (current.getOpeningMessage().isBlank()) current.setOpeningMessage(generated.getOpeningMessage()); if (current.getLearningPlan().isEmpty()) current.setLearningPlan(generated.getLearningPlan());
            if (current.getAiConfig() == null || current.getAiConfig().getTeachingApproach() == null) current.setAiConfig(generated.getAiConfig());
            generated = current;
        }
        sessions.validateContent(generated, JSONUtil.toList(session.getMaterialIdsJson(), String.class), false);
        session.setContentJson(JSONUtil.toJsonStr(generated)); session.setLearningGoals(String.join("\n", generated.getLearningGoals()));
        if (!"import".equals(job.getKind()) || session.getDescription().isBlank())
            session.setDescription(Objects.toString(generated.getDescription(), ""));
        if (!sessions.updateById(session)) throw error(409, "Task changed. Generated result was retained.");
        lambdaUpdate().eq(GenerationJob::getId, id).eq(GenerationJob::getStatus, "succeeded").set(GenerationJob::getStatus, "applied").set(GenerationJob::getUpdatedAt, LocalDateTime.now(ZoneOffset.UTC)).update();
        return session;
    }
    @Override public Map<String, Object> view(GenerationJob job) {
        Map<String, Object> result = new LinkedHashMap<>(); result.put("id", job.getId()); result.put("sessionId", job.getSessionId());
        result.put("status", job.getStatus()); result.put("stage", job.getStage()); result.put("errorMessage", job.getErrorMessage());
        result.put("expectedRevision", job.getExpectedRevision()); result.put("createdAt", job.getCreatedAt());
        var usage = job.getUsageJson() == null ? new JSONObject() : JSONUtil.parseObj(job.getUsageJson());
        result.put("progressCharacters", usage.getInt("charactersReceived", 0));
        result.put("usage", usage.containsKey("window") ? usage : null);
        JSONObject savedResult = job.getResultJson() == null ? null : JSONUtil.parseObj(job.getResultJson());
        result.put("diagnosticResponse", savedResult == null ? null : savedResult.getStr("rawResponse"));
        result.put("result", savedResult == null || savedResult.containsKey("rawResponse") ? null : savedResult); return result;
    }
    @Override public void recoverProcessing() {
        lambdaUpdate().eq(GenerationJob::getStatus, "running").set(GenerationJob::getStatus, "failed")
            .set(GenerationJob::getErrorMessage, "Generation was interrupted. Retry when ready.").set(GenerationJob::getUpdatedAt, LocalDateTime.now(ZoneOffset.UTC)).update();
    }
    @Override public void processNext() {
        List<GenerationJob> jobs = lambdaQuery().eq(GenerationJob::getStatus, "queued").orderByAsc(GenerationJob::getCreatedAt)
            .page(new com.baomidou.mybatisplus.extension.plugins.pagination.Page<GenerationJob>(1, 1, false)).getRecords();
        if (jobs.isEmpty()) return;
        GenerationJob job = jobs.get(0);
        if (!lambdaUpdate().eq(GenerationJob::getId, job.getId()).eq(GenerationJob::getStatus, "queued").set(GenerationJob::getStatus, "running").set(GenerationJob::getStage, "planning").update()) return;
        try {
            AccountUser owner = accounts.getById(job.getOwnerId());
            if (owner == null || Boolean.TRUE.equals(owner.getArchived())) throw error(403, "Generation owner is unavailable");
            TeachingSession session = sessions.require(job.getSessionId(), owner, true);
            if (!session.getRevision().equals(job.getExpectedRevision())) throw error(409, "Task changed before generation started");
            List<String> ids = JSONUtil.toList(session.getMaterialIdsJson(), String.class);
            Requests.Generation input = JSONUtil.toBean(job.getRequestJson(), Requests.Generation.class);
            job.setStage("materials");
            List<CourseMaterial> selected = materials.selected(session.getCourseId(), ids);
            materials.requireProcessed(selected);
            job.setStage("requesting");
            lambdaUpdate().eq(GenerationJob::getId, job.getId()).set(GenerationJob::getStage, "drafting").update();
            long[] nextProgress = {0};
            java.util.function.IntConsumer progress = characters -> {
                long now = System.nanoTime();
                if (characters > 0 && now < nextProgress[0]) return;
                nextProgress[0] = now + java.util.concurrent.TimeUnit.SECONDS.toNanos(2);
                lambdaUpdate().eq(GenerationJob::getId, job.getId()).eq(GenerationJob::getStatus, "running")
                    .set(GenerationJob::getUsageJson, JSONUtil.toJsonStr(Map.of("charactersReceived", characters))).update();
            };
            java.util.function.Consumer<zzm.integration.QwenClient.Completion> received = response -> {
                job.setStage("structuring");
                lambdaUpdate().eq(GenerationJob::getId, job.getId())
                    .set(GenerationJob::getResultJson, JSONUtil.toJsonStr(Map.of("rawResponse", response.text())))
                    .set(GenerationJob::getUsageJson, JSONUtil.toJsonStr(response.usage())).set(GenerationJob::getStage, "structuring").update();
            };
            var generated = "revise".equals(job.getKind())
                ? ai.revise(session, courses.getById(session.getCourseId()), selected, input.getInstruction(), progress, received)
                : ai.generate(session, courses.getById(session.getCourseId()), selected, "import".equals(job.getKind()), input.getSourceMaterialIds(), progress, received);
            TaskContent content = generated.content();
            job.setStage("validating");
            lambdaUpdate().eq(GenerationJob::getId, job.getId()).set(GenerationJob::getUsageJson, JSONUtil.toJsonStr(generated.usage())).set(GenerationJob::getStage, "validating").update();
            sessions.validateContent(content, ids, !"import".equals(job.getKind()));
            if ("import".equals(job.getKind())) {
                if (content.getQuestions().isEmpty()) throw error(422, "No questions were extracted from the selected source materials.");
                for (TaskContent.Question question : content.getQuestions()) {
                    if (question.getSourceMaterialIds().isEmpty() || !input.getSourceMaterialIds().containsAll(question.getSourceMaterialIds()))
                        throw error(422, "Imported questions must reference only the selected question source materials. Review the model response and retry.");
                }
            }
            if (!"import".equals(job.getKind()) && (content.getHandout().isBlank() || content.getOpeningMessage().isBlank())) throw error(502, "AI did not return a complete handout and opening message. Retry generation.");
            lambdaUpdate().eq(GenerationJob::getId, job.getId()).set(GenerationJob::getStatus, "succeeded").set(GenerationJob::getStage, "ready")
                .set(GenerationJob::getResultJson, JSONUtil.toJsonStr(content)).set(GenerationJob::getUpdatedAt, LocalDateTime.now(ZoneOffset.UTC)).update();
        } catch (Exception exception) {
            String prefix = switch (Objects.toString(job.getStage(), "")) {
                case "materials" -> "Material preparation failed";
                case "structuring" -> "Model output parsing failed";
                case "validating" -> "Question validation failed";
                default -> "AI request failed";
            };
            String detail = exception instanceof ResponseStatusException status ? status.getReason()
                : "Generation processing failed (" + exception.getClass().getSimpleName() + ")";
            String message = prefix + ": " + detail;
            lambdaUpdate().eq(GenerationJob::getId, job.getId()).set(GenerationJob::getStatus, "failed").set(GenerationJob::getErrorMessage, message)
                .set(GenerationJob::getStage, job.getStage())
                .set(GenerationJob::getUpdatedAt, LocalDateTime.now(ZoneOffset.UTC)).update();
        }
    }
}
