package cn.aicademiya.service.impl;

import cn.aicademiya.dto.*;
import cn.aicademiya.entity.*;
import cn.aicademiya.mapper.GenerationJobMapper;
import cn.aicademiya.service.*;
import cn.hutool.json.*;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import java.time.*;
import java.util.*;
import static cn.aicademiya.exception.ApiErrors.error;

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

    @Override public Map<String, Object> assistTeacher(Requests.Chat input, AccountUser user) {
        accounts.requireStaff(user);
        String context = input.getCourseId() == null || input.getCourseId().isBlank() ? ""
            : JSONUtil.toJsonStr(courses.view(courses.requireAccess(input.getCourseId(), user, true), user));
        String response = ai.chat("You assist a teacher with course planning. Answer in the user's language. You can suggest actions but cannot claim to have saved or published changes. Course context: "
            + context, input.getHistory(), input.getMessage());
        return Map.of("message", response);
    }

    @Override @Transactional public GenerationJob start(String sessionId, Requests.Generation input, AccountUser user) {
        TeachingSession session = sessions.require(sessionId, user, true);
        if (!session.getRevision().equals(input.getRevision())) throw error(409, "Save or reload the latest task before generating");
        if (lambdaQuery().eq(GenerationJob::getSessionId, sessionId).in(GenerationJob::getStatus, "queued", "running").count() > 0) throw error(409, "Generation is already running");
        List<String> ids = JSONUtil.toList(session.getMaterialIdsJson(), String.class);
        List<CourseMaterial> selected = materials.selected(session.getCourseId(), ids);
        if (selected.isEmpty()) throw error(422, "Select processed materials with readable content");
        materials.requireProcessed(selected);
        if ("import".equals(input.getKind()) && !ids.contains(input.getSourceMaterialId())) throw error(422, "Select the worksheet material to import");
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
            if (current.getLearningPlan().isEmpty()) current.setLearningPlan(generated.getLearningPlan());
            if (current.getAiConfig() == null || current.getAiConfig().getTeachingApproach() == null) current.setAiConfig(generated.getAiConfig());
            generated = current;
        }
        sessions.validateContent(generated, JSONUtil.toList(session.getMaterialIdsJson(), String.class), false);
        session.setContentJson(JSONUtil.toJsonStr(generated)); session.setLearningGoals(String.join("\n", generated.getLearningGoals()));
        if (session.getDescription().isBlank()) session.setDescription(Objects.toString(generated.getDescription(), ""));
        if (!sessions.updateById(session)) throw error(409, "Task changed. Generated result was retained.");
        lambdaUpdate().eq(GenerationJob::getId, id).eq(GenerationJob::getStatus, "succeeded").set(GenerationJob::getStatus, "applied").set(GenerationJob::getUpdatedAt, LocalDateTime.now(ZoneOffset.UTC)).update();
        return session;
    }
    @Override public Map<String, Object> view(GenerationJob job) {
        Map<String, Object> result = new LinkedHashMap<>(); result.put("id", job.getId()); result.put("sessionId", job.getSessionId());
        result.put("status", job.getStatus()); result.put("stage", job.getStage()); result.put("errorMessage", job.getErrorMessage());
        result.put("expectedRevision", job.getExpectedRevision()); result.put("createdAt", job.getCreatedAt());
        result.put("result", job.getResultJson() == null ? null : JSONUtil.parseObj(job.getResultJson())); return result;
    }
    @Override public void recoverProcessing() {
        lambdaUpdate().eq(GenerationJob::getStatus, "running").set(GenerationJob::getStatus, "failed")
            .set(GenerationJob::getErrorMessage, "Generation was interrupted. Retry when ready.").set(GenerationJob::getUpdatedAt, LocalDateTime.now(ZoneOffset.UTC)).update();
    }
    @Override public void processNext() {
        List<GenerationJob> jobs = lambdaQuery().eq(GenerationJob::getStatus, "queued").orderByAsc(GenerationJob::getCreatedAt)
            .page(new com.baomidou.mybatisplus.extension.plugins.pagination.Page<GenerationJob>(1, 1, false)).getRecords();
        if (jobs.isEmpty()) return;
        GenerationJob job = jobs.getFirst();
        if (!lambdaUpdate().eq(GenerationJob::getId, job.getId()).eq(GenerationJob::getStatus, "queued").set(GenerationJob::getStatus, "running").set(GenerationJob::getStage, "planning").update()) return;
        try {
            AccountUser owner = accounts.getById(job.getOwnerId());
            if (owner == null || Boolean.TRUE.equals(owner.getArchived())) throw error(403, "Generation owner is unavailable");
            TeachingSession session = sessions.require(job.getSessionId(), owner, true);
            if (!session.getRevision().equals(job.getExpectedRevision())) throw error(409, "Task changed before generation started");
            List<String> ids = JSONUtil.toList(session.getMaterialIdsJson(), String.class);
            Requests.Generation input = JSONUtil.toBean(job.getRequestJson(), Requests.Generation.class);
            List<CourseMaterial> selected = materials.selected(session.getCourseId(), ids);
            materials.requireProcessed(selected);
            TaskContent content = ai.generate(session, courses.getById(session.getCourseId()), selected, "import".equals(job.getKind()), input.getSourceMaterialId());
            lambdaUpdate().eq(GenerationJob::getId, job.getId()).set(GenerationJob::getStage, "validating").update();
            sessions.validateContent(content, ids, !"import".equals(job.getKind()));
            lambdaUpdate().eq(GenerationJob::getId, job.getId()).set(GenerationJob::getStatus, "succeeded").set(GenerationJob::getStage, "ready")
                .set(GenerationJob::getResultJson, JSONUtil.toJsonStr(content)).set(GenerationJob::getUpdatedAt, LocalDateTime.now(ZoneOffset.UTC)).update();
        } catch (Exception exception) {
            String message = exception instanceof ResponseStatusException status ? status.getReason() : "AI generation failed. Check the model configuration and retry.";
            lambdaUpdate().eq(GenerationJob::getId, job.getId()).set(GenerationJob::getStatus, "failed").set(GenerationJob::getErrorMessage, message)
                .set(GenerationJob::getUpdatedAt, LocalDateTime.now(ZoneOffset.UTC)).update();
        }
    }
}
