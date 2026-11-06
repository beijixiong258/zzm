package zzm.service.impl;

import zzm.dto.*;
import zzm.entity.*;
import zzm.mapper.LearningRecordMapper;
import zzm.mapper.LearningRecordHistoryMapper;
import zzm.config.AppProperties;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import lombok.extern.slf4j.Slf4j;
import java.nio.charset.StandardCharsets;
import zzm.service.*;
import zzm.integration.QmdClient;
import zzm.dto.RetrievalContent.*;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.UserMessage;
import cn.hutool.json.*;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import lombok.RequiredArgsConstructor;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.*;
import java.util.*;
import static zzm.exception.ApiErrors.error;

@Slf4j
@Service
@RequiredArgsConstructor
public class LearningServiceImpl extends ServiceImpl<LearningRecordMapper, LearningRecord> implements LearningService {
    private final SessionService sessions;
    private final CourseService courses;
    private final MaterialService materials;
    private final AiService ai;
    private final AppProperties properties;
    private final LearningRecordHistoryMapper histories;
    private final AccountService accounts;
    private final TaskExporter exporter;
    private final TutorContext tutor;
    private final ContextBudget budget;
    private final QmdClient qmd;
    private final PdfInputReader pdf;
    @Override public byte[] exportResult(String id, AccountUser user, String materialBaseUrl) {
        if (!"student".equals(user.getRole())) throw error(403, "Only students can export their own learning results");
        LearningRecord record = owned(id, user, false);
        if (Boolean.TRUE.equals(record.getPreview())) throw error(403, "Preview records cannot be exported");
        Map<String, Object> task = sessions.studentProjection(snapshot(record));
        JSONArray messages = JSONUtil.parseArray(record.getMessagesJson());
        filterPrivateFeedback(messages);
        List<Map<String, Object>> files = attachments(id, user);
        return exporter.exportResult(task, currentAnswers(record), messages,
            record.getTeacherNote(), files, materialBaseUrl);
    }
    @Override public Map<String, Object> workspace(String sessionId, String versionId, AccountUser user) {
        Map<String, Object> task = sessions.published(sessionId, versionId, user);
        LearningRecord record = latestRecord(sessionId, user.getId());
        Map<String, Object> result = new LinkedHashMap<>(); result.put("task", task); result.put("record", record == null ? null : view(record)); return result;
    }
    @Override public LearningRecord start(String sessionId, String versionId, AccountUser user) {
        if (!"student".equals(user.getRole())) throw error(403, "Student access required");
        Map<String, Object> task = sessions.published(sessionId, versionId, user);
        String selected = Objects.toString(task.get("versionId"));
        LearningRecord existing = latestRecord(sessionId, user.getId());
        if (existing != null) {
            if ("notStarted".equals(existing.getStatus())) { existing.setStatus("inProgress"); existing.setStartedAt(LocalDateTime.now(ZoneOffset.UTC)); saveRevision(existing, existing.getRevision()); }
            return existing;
        }
        LearningRecord record = new LearningRecord(); record.setSessionId(sessionId); record.setUserId(user.getId()); record.setVersionId(selected);
        record.setSnapshotJson(JSONUtil.toJsonStr(task));
        record.setPreview(false); record.setStatus("inProgress"); record.setAnswersJson("{}"); record.setMessagesJson("[]"); record.setRevision(0L);
        record.setTeacherNote(""); record.setStartedAt(LocalDateTime.now(ZoneOffset.UTC)); record.setUpdatedAt(record.getStartedAt());
        JSONObject content = JSONUtil.parseObj(task.get("content"));
        String opening = content.getStr("openingMessage", "");
        if (!opening.isBlank()) {
            Requests.ChatMessage message = new Requests.ChatMessage(); message.setRole("assistant"); message.setContent(opening); message.setCreatedAt(Instant.now().toString());
            record.setMessagesJson(JSONUtil.toJsonStr(List.of(message)));
        }
        try { save(record); } catch (DuplicateKeyException exception) {
            return latestRecord(sessionId, user.getId());
        }
        return record;
    }
    private LearningRecord latestRecord(String sessionId, String userId) {
        return lambdaQuery().eq(LearningRecord::getSessionId, sessionId).eq(LearningRecord::getUserId, userId)
            .eq(LearningRecord::getPreview, false).orderByDesc(LearningRecord::getUpdatedAt).orderByDesc(LearningRecord::getId)
            .last("LIMIT 1").one();
    }
    private LearningRecord owned(String id, AccountUser user, boolean editable) {
        LearningRecord record = getById(id);
        if (record == null || !record.getUserId().equals(user.getId())) throw error(404, "Learning record not found");
        if (Boolean.TRUE.equals(record.getPreview())) sessions.require(record.getSessionId(), user, true); else sessions.published(record.getSessionId(), record.getVersionId(), user);
        if (editable && Set.of("submitted", "confirmed").contains(record.getStatus())) throw error(409, "This submission is read-only until your teacher requests a revision");
        return record;
    }
    private void saveRevision(LearningRecord record, long expected) {
        if (record.getRevision() != expected) throw error(409, "Learning record changed. Reload before saving.");
        if ("notStarted".equals(record.getStatus())) { record.setStatus("inProgress"); record.setStartedAt(LocalDateTime.now(ZoneOffset.UTC)); }
        record.setUpdatedAt(LocalDateTime.now(ZoneOffset.UTC));
        if (!updateById(record)) throw error(409, "Learning record changed. Reload before saving.");
    }
    @Override @Transactional public Map<String, Object> saveAnswers(String id, Requests.Answer input, AccountUser user) {
        LearningRecord record = owned(id, user, true);
        TaskContent content = snapshot(record).getBean("content", TaskContent.class);
        Set<String> ids = new HashSet<>(); content.getQuestions().forEach(q -> ids.add(q.getId()));
        JSONObject savedAnswers = JSONUtil.parseObj(record.getAnswersJson());
        Set<String> knownIds = new HashSet<>(ids); knownIds.addAll(savedAnswers.keySet());
        if (!knownIds.containsAll(input.getAnswers().keySet()) || input.getAnswers().values().stream().anyMatch(v -> v == null || v.length() > 20000)) throw error(422, "Invalid answer data");
        Map<String, String> answers = new LinkedHashMap<>();
        currentAnswers(record, content).forEach((key, value) -> answers.put(key, Objects.toString(value, "")));
        input.getAnswers().forEach((key, value) -> { if (ids.contains(key)) answers.put(key, value); });
        for (TaskContent.Question question : content.getQuestions()) {
            if (!"multipleChoice".equals(question.getType()) || !answers.containsKey(question.getId())) continue;
            List<String> selected = TaskContent.multipleChoiceAnswers(answers.get(question.getId()), question.getOptions());
            if (!question.getOptions().containsAll(selected)) throw error(422, "Invalid answer data");
            answers.put(question.getId(), selected.isEmpty() ? "" : JSONUtil.toJsonStr(selected));
        }
        if (!record.getRevision().equals(input.getRevision())) throw error(409, "Learning record changed. Reload before saving.");
        if (JSONUtil.parseObj(record.getAnswersJson()).equals(JSONUtil.parseObj(answers))) return view(record);
        Map<String, Object> previous = Map.of("revision", record.getRevision(), "savedAt", Instant.now().toString(),
            "answers", JSONUtil.parseObj(record.getAnswersJson()), "questions", historyQuestions(record));
        // 在检查历史记录外键前，先更新带版本号的父记录并取得行锁。
        record.setSnapshotJson(snapshot(record).toString());
        record.setAnswersJson(JSONUtil.toJsonStr(answers)); saveRevision(record, input.getRevision());
        appendHistory(record, "answer", previous, null); return view(record);
    }
    @Override @Transactional public Map<String, Object> resetConversation(String id, long revision, AccountUser user) {
        LearningRecord record = owned(id,user,true);
        List<Requests.ChatMessage> messages = JSONUtil.toList(record.getMessagesJson(),Requests.ChatMessage.class);
        if(messages.stream().anyMatch(Requests.ChatMessage::isPendingReview)) throw error(409,"Your AI feedback is awaiting teacher review");
        Map<String, Object> previous = Map.of("archivedAt", Instant.now().toString(), "messages", messages);
        String opening = snapshot(record).getJSONObject("content").getStr("openingMessage","");
        List<Requests.ChatMessage> next=new ArrayList<>();
        if(!opening.isBlank()){var message=new Requests.ChatMessage();message.setRole("assistant");message.setContent(opening);message.setCreatedAt(Instant.now().toString());next.add(message);}
        record.setTutorStateJson(JSONUtil.toJsonStr(new TutorState()));
        record.setMessagesJson(JSONUtil.toJsonStr(next));saveRevision(record,revision);
        appendHistory(record, "conversation", previous, messages.size());return view(record);
    }
    @Override public Map<String, Object> context(String id, Requests.Chat input, AccountUser user) {
        LearningRecord record = owned(id, user, true);
        if (input.getAnswers() != null) record.setAnswersJson(JSONUtil.toJsonStr(input.getAnswers()));
        List<Requests.ChatMessage> history = JSONUtil.toList(record.getMessagesJson(), Requests.ChatMessage.class);
        requireConversationRoom(history.size());
        JSONObject snapshot = snapshot(record);
        TaskContent content = snapshot.getBean("content", TaskContent.class);
        TutorState state = record.getTutorStateJson() == null ? new TutorState() : JSONUtil.toBean(record.getTutorStateJson(), TutorState.class);
        var focus = tutor.focus(content, input, state);
        var messages = tutor.messages(snapshot, content, currentAnswers(record, content), focus, state, history, input);
        var result = budget.studentDescribe(messages, properties.getTutor(), properties.getAi().getChatMaxTokens() == null ? 4096 : properties.getAi().getChatMaxTokens(), 0, 1800);
        result.put("retrievalReserve", properties.getTutor().getMaterialTokens());
        result.put("estimateBeforeRetrieval", true);
        return result;
    }
    @Override public Map<String, Object> chat(String id, Requests.Chat input, AccountUser user) {
        LearningRecord record = owned(id, user, true);
        List<Requests.ChatMessage> messages = JSONUtil.toList(record.getMessagesJson(), Requests.ChatMessage.class);
        if (messages.stream().anyMatch(m -> input.getRequestId().equals(m.getRequestId()) && "assistant".equals(m.getRole()))) return view(record);
        if (input.getRevision() == null || !record.getRevision().equals(input.getRevision())) throw error(409, "Learning record changed. Reload before sending.");
        JSONObject snapshot = snapshot(record);
        if (messages.stream().anyMatch(Requests.ChatMessage::isPendingReview)) throw error(409, "Your AI feedback is awaiting teacher review");
        requireConversationRoom(messages.size());
        long started = System.nanoTime();
        TutorTurn turn = new TutorTurn(record, snapshot, messages, input, user);
        turn.summarise();
        var context = tutor.messages(snapshot, turn.content, turn.answers, turn.focus, turn.state, messages, input);
        turn.prefetch(context);
        var response = ai.studentReply(context, turn);
        turn.validate();
        response.usage().put("summaryUsage", turn.summaryUsage);
        response.usage().put("retrievalMs", turn.retrievalMs);
        response.usage().put("searchCalls", turn.searchCalls);
        response.usage().put("endToEndMs", java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started));
        if (!turn.summaryUsage.isEmpty()) {
            long summaryInput = ((Number) turn.summaryUsage.getOrDefault("promptTokensActual", 0)).longValue();
            long summaryOutput = ((Number) turn.summaryUsage.getOrDefault("completionTokensActual", 0)).longValue();
            response.usage().put("allModelInputTokens", ((Number) response.usage().getOrDefault("promptTokensActual", 0)).longValue() + summaryInput);
            response.usage().put("allModelOutputTokens", ((Number) response.usage().getOrDefault("completionTokensActual", 0)).longValue() + summaryOutput);
        }
        Requests.ChatMessage question = new Requests.ChatMessage(); question.setRole("user"); question.setContent(input.getMessage());
        question.setAttachmentIds(input.getAttachmentIds()); question.setRequestId(input.getRequestId()); question.setCreatedAt(Instant.now().toString());
        Requests.ChatMessage answer = new Requests.ChatMessage(); answer.setRole("assistant"); answer.setContent(response.text()); answer.setUsage(response.usage()); answer.setPendingReview("teacherReview".equals(snapshot.getJSONObject("content").getStr("feedbackMode")));
        answer.setRequestId(input.getRequestId()); answer.setCreatedAt(Instant.now().toString()); messages.add(question); messages.add(answer);
        record.setTutorStateJson(JSONUtil.toJsonStr(turn.state));
        record.setMessagesJson(JSONUtil.toJsonStr(messages)); saveRevision(record, input.getRevision()); return view(record);
    }
    @Override public Map<String, Object> submit(String id, long revision, AccountUser user) {
        LearningRecord record = owned(id, user, true);
        TaskContent content = snapshot(record).getBean("content", TaskContent.class);
        JSONObject answers = currentAnswers(record, content);
        List<CourseMaterial> submittedFiles = materials.lambdaQuery().eq(CourseMaterial::getRecordId,id).eq(CourseMaterial::getOwnerId,user.getId())
            .eq(CourseMaterial::getArchived,false).in(CourseMaterial::getStatus,"ready","needsReview").list();
        materials.requireProcessed(submittedFiles);
        Set<String> attachedQuestions = new HashSet<>(); submittedFiles.forEach(file -> {if(file.getQuestionId()!=null)attachedQuestions.add(file.getQuestionId());});
        if (content.getQuestions().stream().anyMatch(q -> answers.getStr(q.getId(), "").isBlank() && !attachedQuestions.contains(q.getId()))) throw error(422, "Answer all questions or upload a processed question attachment before submitting");
        record.setStatus("submitted"); record.setSubmittedAt(LocalDateTime.now(ZoneOffset.UTC)); saveRevision(record, revision); return view(record);
    }
    @Override public List<Map<String, Object>> roster(String sessionId, String versionId, AccountUser user) {
        TeachingSession session = sessions.require(sessionId, user, true);
        String selected = session.getPublishedVersionId();
        TaskContent content = selected == null ? JSONUtil.toBean(session.getContentJson(), TaskContent.class)
            : JSONUtil.parseObj(sessions.version(sessionId, selected).getContentJson()).getBean("content", TaskContent.class);
        Map<String, LearningRecord> recordsByUser = new HashMap<>();
        lambdaQuery().eq(LearningRecord::getSessionId, sessionId).eq(LearningRecord::getPreview, false)
            .orderByDesc(LearningRecord::getUpdatedAt).orderByDesc(LearningRecord::getId).list()
            .forEach(record -> recordsByUser.putIfAbsent(record.getUserId(), record));
        Map<String,Set<String>> attachmentAnswers = new HashMap<>();
        if(!recordsByUser.isEmpty()) materials.lambdaQuery().in(CourseMaterial::getRecordId,recordsByUser.values().stream().map(LearningRecord::getId).toList())
            .eq(CourseMaterial::getArchived,false).in(CourseMaterial::getStatus,"ready","needsReview").list().forEach(file -> {
                if(file.getQuestionId()!=null && !file.getQuestionId().isBlank()) attachmentAnswers.computeIfAbsent(file.getRecordId(), k->new HashSet<>()).add(file.getQuestionId());
            });
        return courses.students(session.getCourseId()).stream().map(student -> {
            LearningRecord record = recordsByUser.get(student.getId());
            Map<String, Object> result = new LinkedHashMap<>(); result.put("userId", student.getId()); result.put("name", student.getName()); result.put("email", Objects.toString(student.getEmail(), student.getUsername()));
            result.put("recordId", record == null ? null : record.getId()); result.put("versionId", selected);
            result.put("status", record == null || "notStarted".equals(record.getStatus()) ? "notStarted" : "confirmed".equals(record.getStatus()) ? "completed" : "inProgress");
            result.put("submissionStatus", record == null ? "notStarted" : record.getStatus()); result.put("total", content.getQuestions().size());
            JSONObject answers = record == null ? new JSONObject() : currentAnswers(record, content);
            result.put("answered", content.getQuestions().stream().filter(q -> !answers.getStr(q.getId(), "").isBlank() || record != null && attachmentAnswers.getOrDefault(record.getId(),Set.of()).contains(q.getId())).count());
            result.put("lastActive", record == null ? null : record.getUpdatedAt()); return result;
        }).toList();
    }
    @Override public Map<String, Object> observe(String id, AccountUser user) {
        LearningRecord record = getById(id); if (record == null) throw error(404, "Learning record not found");
        sessions.require(record.getSessionId(), user, true);
        if (Boolean.TRUE.equals(record.getPreview()) && !record.getUserId().equals(user.getId())) throw error(403, "Simulation access denied"); return Map.of("task", snapshot(record), "record", recordView(record, true), "attachments", attachments(id, user));
    }
    @Override public Map<String, Object> review(String id, Requests.Review input, AccountUser user) {
        LearningRecord record = getById(id); if (record == null) throw error(404, "Learning record not found");
        sessions.require(record.getSessionId(), user, true);
        if (!Set.of("submitted", "confirmed", "needsRevision").contains(record.getStatus())) throw error(409, "The student has not submitted this task");
        record.setStatus(input.getStatus()); record.setTeacherNote(input.getTeacherNote()); record.setReviewedAt(LocalDateTime.now(ZoneOffset.UTC));
        saveRevision(record, input.getRevision()); return recordView(record, true);
    }
    @Override public List<Map<String, Object>> history(AccountUser user) {
        if (Boolean.TRUE.equals(user.getMustChangePassword())) throw error(403, "Password change required");
        List<String> courseIds = courses.mine(user).stream().filter(course -> !Boolean.TRUE.equals(course.get("archived")))
            .map(course -> Objects.toString(course.get("id"))).toList();
        if (courseIds.isEmpty()) return List.of();
        List<String> sessionIds = sessions.lambdaQuery().in(TeachingSession::getCourseId, courseIds)
            .eq(TeachingSession::getArchived, false).list().stream().map(TeachingSession::getId).toList();
        if (sessionIds.isEmpty()) return List.of();
        Set<String> seenTasks = new HashSet<>();
        return lambdaQuery().select(LearningRecord::getId, LearningRecord::getSessionId, LearningRecord::getVersionId,
            LearningRecord::getUserId, LearningRecord::getStatus, LearningRecord::getUpdatedAt)
            .eq(LearningRecord::getUserId, user.getId()).eq(LearningRecord::getPreview, false)
            .in(LearningRecord::getSessionId, sessionIds).orderByDesc(LearningRecord::getUpdatedAt).orderByDesc(LearningRecord::getId)
            .list().stream().filter(record -> seenTasks.add(record.getSessionId())).map(record -> {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("id", record.getId()); item.put("sessionId", record.getSessionId()); item.put("versionId", record.getVersionId());
                item.put("userId", record.getUserId()); item.put("status", record.getStatus()); item.put("updatedAt", record.getUpdatedAt()); return item;
            }).toList();
    }
    private JSONObject snapshot(LearningRecord record) {
        return JSONUtil.parseObj(Boolean.TRUE.equals(record.getPreview()) ? record.getSnapshotJson()
            : sessions.version(record.getSessionId(), null).getContentJson());
    }
    private JSONObject currentAnswers(LearningRecord record) {
        return currentAnswers(record, snapshot(record).getBean("content", TaskContent.class));
    }
    private JSONObject currentAnswers(LearningRecord record, TaskContent content) {
        JSONObject saved = JSONUtil.parseObj(record.getAnswersJson()), result = new JSONObject();
        for (TaskContent.Question question : content.getQuestions()) {
            if (!saved.containsKey(question.getId())) continue;
            String answer = saved.getStr(question.getId(), "");
            boolean valid = answer.isBlank() || switch (question.getType()) {
                case "singleChoice", "trueFalse" -> question.getOptions().contains(answer);
                case "multipleChoice" -> question.getOptions().containsAll(TaskContent.multipleChoiceAnswers(answer, question.getOptions()));
                default -> true;
            };
            if (valid) result.set(question.getId(), answer);
        }
        return result;
    }
    private List<LearningRecord> relatedRecords(LearningRecord record) {
        if (Boolean.TRUE.equals(record.getPreview())) return List.of(record);
        return lambdaQuery().eq(LearningRecord::getSessionId, record.getSessionId()).eq(LearningRecord::getUserId, record.getUserId())
            .eq(LearningRecord::getPreview, false).orderByDesc(LearningRecord::getUpdatedAt).orderByDesc(LearningRecord::getId).list();
    }
    private List<Map<String, Object>> historyQuestions(LearningRecord record) {
        JSONObject original = record.getSnapshotJson() == null
            ? JSONUtil.parseObj(sessions.version(record.getSessionId(), record.getVersionId()).getContentJson())
            : JSONUtil.parseObj(record.getSnapshotJson());
        Map<String, Map<String, Object>> questions = new LinkedHashMap<>();
        for (JSONObject source : List.of(original, snapshot(record))) {
            JSONArray items = source.getJSONObject("content").getJSONArray("questions");
            if (items == null) continue;
            for (Object item : items) {
                JSONObject question = JSONUtil.parseObj(item);
                Map<String, Object> visible = new LinkedHashMap<>(question);
                visible.remove("referenceAnswer"); visible.remove("explanation");
                questions.putIfAbsent(question.getStr("id"), visible);
            }
        }
        return new ArrayList<>(questions.values());
    }
    @Override public Map<String, Object> previewWorkspace(String id, AccountUser user) {
        var session = sessions.require(id, user, true);
        Map<String, Object> task = sessions.view(session, true);
        LearningRecord record = lambdaQuery().eq(LearningRecord::getSessionId, id).eq(LearningRecord::getUserId, user.getId())
            .eq(LearningRecord::getPreview, true).orderByDesc(LearningRecord::getUpdatedAt).last("LIMIT 1").one();
        if (record != null) { JSONObject saved = snapshot(record); if (!Objects.equals(saved.getLong("revision"), session.getRevision()) || !Objects.equals(saved.getStr("courseInformation", ""), Objects.toString(task.get("courseInformation"), "")) || !Objects.equals(saved.getStr("studentProfile", ""), Objects.toString(task.get("studentProfile"), "")) || !Objects.equals(saved.getStr("courseInstructions", ""), Objects.toString(task.get("courseInstructions"), ""))) record = null; }
        Map<String,Object> result = new LinkedHashMap<>(); result.put("task", sessions.studentProjection(task));
        result.put("record", record == null ? null : view(record)); return result;
    }
    @Override public LearningRecord startPreview(String id, AccountUser user) {
        var session = sessions.require(id, user, true);
        Map<String,Object> task = sessions.view(session, true);
        LearningRecord record = new LearningRecord(); record.setSessionId(id); record.setUserId(user.getId()); record.setPreview(true);
        record.setSnapshotJson(JSONUtil.toJsonStr(task)); record.setStatus("inProgress"); record.setRevision(0L);
        record.setAnswersJson("{}"); record.setMessagesJson("[]"); record.setTeacherNote("");
        record.setStartedAt(LocalDateTime.now(ZoneOffset.UTC)); record.setUpdatedAt(record.getStartedAt());
        String opening = JSONUtil.parseObj(task.get("content")).getStr("openingMessage", "");
        if (!opening.isBlank()) {
            Requests.ChatMessage message = new Requests.ChatMessage(); message.setRole("assistant"); message.setContent(opening); message.setCreatedAt(Instant.now().toString());
            record.setMessagesJson(JSONUtil.toJsonStr(List.of(message)));
        }
        save(record); return record;
    }
    @Override public List<Map<String,Object>> attachments(String id, AccountUser user) {
        LearningRecord record = getById(id);
        if (record == null) throw error(404, "Learning record not found");
        if (record.getUserId().equals(user.getId())) owned(id, user, false);
        else { sessions.require(record.getSessionId(), user, true); if (Boolean.TRUE.equals(record.getPreview())) throw error(403, "Simulation access denied"); }
        return materials.lambdaQuery().eq(CourseMaterial::getRecordId, id).eq(CourseMaterial::getArchived, false)
            .orderByAsc(CourseMaterial::getCreatedAt).list().stream().map(materials::view).toList();
    }
    @Override @Transactional public Map<String,Object> uploadAttachment(String id, String questionId, org.springframework.web.multipart.MultipartFile file, AccountUser user) {
        LearningRecord record = owned(id, user, true);
        record = baseMapper.lockById(id);
        if (Set.of("submitted", "confirmed").contains(record.getStatus())) throw error(409, "This submission is read-only until your teacher requests a revision");
        JSONObject snapshot = snapshot(record);
        if (questionId != null && !questionId.isBlank() && snapshot.getBean("content", TaskContent.class).getQuestions().stream().noneMatch(q -> questionId.equals(q.getId()))) throw error(422, "Question not found in this task");
        if (materials.lambdaQuery().eq(CourseMaterial::getRecordId, id).eq(CourseMaterial::getArchived, false).count() >= 100) throw error(422, "This learning record has reached its attachment limit");
        return materials.view(materials.uploadForRecord(snapshot.getStr("courseId"), id, questionId, file, user));
    }
    @Override @Transactional public Map<String,Object> removeAttachment(String id, String attachmentId, long revision, AccountUser user) {
        LearningRecord record = owned(id, user, true);
        CourseMaterial attachment = materials.getById(attachmentId);
        if (attachment == null || !id.equals(attachment.getRecordId()) || !user.getId().equals(attachment.getOwnerId()))
            throw error(404, "Attachment not found in this learning record");
        if (Boolean.TRUE.equals(attachment.getArchived())) return view(record);
        // 后台任务只能在事务提交后看到此删除标记；修订失败时会一并回滚。
        materials.lambdaUpdate().eq(CourseMaterial::getId, attachmentId).set(CourseMaterial::getArchived, true)
            .set(CourseMaterial::getFileRemovedAt, LocalDateTime.now(ZoneOffset.UTC)).set(CourseMaterial::getRemovedBy, user.getId()).update();
        saveRevision(record, revision);
        return view(record);
    }
    /** 本轮权限、内容和预算只在服务端构造，模型不能提交账号、课程或集合范围。 */
    private final class TutorTurn implements AiService.TutorAccess {
        final LearningRecord record;
        final JSONObject snapshot;
        final TaskContent content;
        final JSONObject answers;
        final List<Requests.ChatMessage> history;
        final Requests.Chat input;
        final AccountUser user;
        final TutorState state;
        final List<TaskContent.Question> focus;
        final Map<String, CourseMaterial> allowed = new LinkedHashMap<>();
        final Map<String, RetrievalDocument> documents = new LinkedHashMap<>();
        final Set<String> publicSources = new HashSet<>(), supplied = new HashSet<>();
        final List<Message> images = new ArrayList<>();
        final String taskFingerprint, materialFingerprint;
        Map<String, Object> summaryUsage = Map.of();
        long retrievalMs;
        int readingTokens, imageTokens, searchCalls;
        final long startedNanos = System.nanoTime();

        TutorTurn(LearningRecord record, JSONObject snapshot, List<Requests.ChatMessage> history, Requests.Chat input, AccountUser user) {
            this.record = record; this.snapshot = snapshot; this.history = history; this.input = input; this.user = user;
            this.content = snapshot.getBean("content", TaskContent.class); this.answers = currentAnswers(record, content);
            this.taskFingerprint = RetrievalContent.hash(snapshot.toString());
            JSONArray references = snapshot.getJSONArray("materials");
            List<String> teacherIds = references == null ? List.of() : references.stream().map(JSONUtil::parseObj).map(m -> m.getStr("id")).toList();
            if (references != null) references.stream().map(JSONUtil::parseObj).filter(m -> "student".equals(m.getStr("visibility")))
                .forEach(m -> publicSources.add(m.getStr("id")));
            if (!teacherIds.isEmpty()) for (CourseMaterial material : materials.listByIds(teacherIds))
                if (snapshot.getStr("courseId").equals(material.getCourseId()) && material.getOwnerId() == null && active(material)) allowed.put(material.getId(), material);
            for (CourseMaterial material : materials.lambdaQuery().eq(CourseMaterial::getRecordId, record.getId())
                .eq(CourseMaterial::getOwnerId, record.getUserId()).eq(CourseMaterial::getArchived, false).isNull(CourseMaterial::getFileRemovedAt).list()) {
                if (active(material)) { allowed.put(material.getId(), material); publicSources.add(material.getId()); }
            }
            for (String id : input.getAttachmentIds()) {
                CourseMaterial file = allowed.get(id);
                if (file == null || !record.getId().equals(file.getRecordId()) || !record.getUserId().equals(file.getOwnerId())) throw error(403, "Attachment access denied");
                materials.requireProcessed(List.of(file));
            }
            materialFingerprint = fingerprint(allowed.values());
            state = tutor.state(record.getTutorStateJson(), RetrievalContent.hash(taskFingerprint + materialFingerprint), history);
            focus = tutor.focus(content, input, state);
            RetrievalDocument lesson = RetrievalContent.createLessonDocument((Boolean.TRUE.equals(record.getPreview()) ? "p-" + record.getId() : "t-" + record.getSessionId()), RetrievalContent.lessonText(snapshot));
            documents.put("lesson", lesson);
            for (CourseMaterial material : allowed.values()) {
                RetrievalContent prepared = RetrievalContent.read(material);
                if (!prepared.isComplete()) {
                    // 索引未准备好时仅保留已存在的文本，不在学生请求中执行 OCR 或重建索引。
                    if (PdfInputReader.isPdf(material) && "images".equals(pdf.report(material).getPdfInputMode())) continue;
                    prepared = new RetrievalContent(); prepared.setSourceKey(RetrievalContent.sourceKey(material));
                    prepared.append(material.getTextContent(), 0, "extracted", !"needsReview".equals(material.getStatus())); prepared.finish();
                }
                documents.put(material.getId(), new RetrievalDocument("m-" + material.getId(), prepared.getRevision(), material.getTitle(), prepared.getParts()));
            }
            state.getSources().removeIf(ref -> {
                String source = Objects.toString(ref.get("sourceId"), "");
                RetrievalDocument document = documents.get(source);
                return document == null || !Objects.equals(ref.get("revision"), document.revision());
            });
        }
        private boolean active(CourseMaterial material) {
            return !Boolean.TRUE.equals(material.getArchived()) && material.getFileRemovedAt() == null && Set.of("ready", "needsReview").contains(material.getStatus());
        }
        private String fingerprint(Collection<CourseMaterial> files) {
            return RetrievalContent.hash(files.stream().sorted(Comparator.comparing(CourseMaterial::getId))
                .map(m -> m.getId() + ":" + RetrievalContent.materialKey(m) + ":" + m.getVisibility() + ":" + m.getCourseId()
                    + ":" + m.getOwnerId() + ":" + m.getRecordId()).collect(java.util.stream.Collectors.joining("\n")));
        }
        @Override public void validate() {
            if (remainingSeconds() <= 0) throw error(504, "The tutor reached its time limit. Narrow the question and try again.");
            LearningRecord current = owned(record.getId(), user, true);
            if (!record.getRevision().equals(current.getRevision()) || !taskFingerprint.equals(RetrievalContent.hash(snapshot(current).toString())))
                throw error(409, "This task or learning record changed during the reply. Reload before sending again.");
            List<CourseMaterial> currentFiles = allowed.isEmpty() ? List.of() : materials.listByIds(allowed.keySet());
            if (currentFiles.size() != allowed.size() || currentFiles.stream().anyMatch(m -> !active(m)) || !materialFingerprint.equals(fingerprint(currentFiles)))
                throw error(409, "The source materials changed during the reply. Reload before sending again.");
        }
        @Override public int remainingSeconds() {
            return properties.getTutor().getTimeoutSeconds() - (int) java.util.concurrent.TimeUnit.NANOSECONDS.toSeconds(System.nanoTime() - startedNanos);
        }
        @Override public long earlierInputTokens() {
            return Math.max(((Number) summaryUsage.getOrDefault("promptTokensActual", 0)).longValue(),
                ((Number) summaryUsage.getOrDefault("turnInputEstimate", 0)).longValue());
        }
        void summarise() {
            int end = tutor.recentStart(history), start = state.getCoveredMessages(), used = 0, until = start;
            for (int i = start; i < end; i++) {
                int size = budget.estimate(history.get(i).getContent()) + 32;
                if (used + size > 4000 && until > start) break;
                used += size; until = i + 1;
            }
            if (until <= start || used < 600 && until - start < 6) return;
            try {
                validate(); var response = ai.summariseLearning(state.getSummary(), history.subList(start, until), remainingSeconds());
                summaryUsage = response.usage();
                JSONObject summary = JSONUtil.parseObj(response.text());
                if (!summary.keySet().containsAll(List.of("confirmed", "inferred", "hintsGiven", "unresolved", "sources"))
                    || budget.estimate(summary.toString()) > properties.getTutor().getSummaryTokens() * 2) return;
                state.setSummary(summary.toString()); state.setCoveredMessages(until);
                state.setCoveredFingerprint(tutor.digest(history.subList(0, until)));
            } catch (org.springframework.web.server.ResponseStatusException exception) {
                if (exception.getStatusCode().value() == 409 || exception.getStatusCode().value() == 403) throw exception;
                log.debug("Learning summary deferred: {}", exception.getClass().getSimpleName());
            } catch (RuntimeException exception) { log.debug("Learning summary deferred: {}", exception.getClass().getSimpleName()); }
        }
        void prefetch(List<Message> context) {
            List<Object> initial = new ArrayList<>();
            if (input.getMessage().matches("(?is).*(最初|一开始|起初|以前|之前|早先|回顾|回忆|历史|上一段|上次|earlier|previous|prior conversation|originally|at first).*")) initial.add(pastAttempts());
            Map<String, String> imageTexts = new LinkedHashMap<>();
            for (String id : input.getAttachmentIds()) {
                initial.add(readPart(id, "s0"));
                CourseMaterial file = allowed.get(id);
                if (Objects.toString(file.getMimeType(), "").startsWith("image/") && file.getTextContent() != null && !file.getTextContent().isBlank())
                    imageTexts.put(id, file.getTextContent());
            }
            for (CourseMaterial material : allowed.values()) if (!input.getAttachmentIds().contains(material.getId())
                && record.getUserId().equals(material.getOwnerId()) && focus.stream().anyMatch(q -> q.getId().equals(material.getQuestionId()))) initial.add(readPart(material.getId(), "s0"));
            if (!imageTexts.isEmpty() || focus.isEmpty() || input.getMessage().matches("(?is).*(材料|讲义|图|表|章节|页|公式|handout|material|figure|diagram|chapter|page|pdf|equation).*")) {
                // 当前截图本身已随作答提供，预检索用它找讲义依据，避免它自己的转写占用候选位置。
                initial.add(search(tutor.retrievalQuery(focus, input, imageTexts.values()), imageTexts.keySet()));
            }
            if (!initial.isEmpty()) context.add(context.size() - 1, new UserMessage("Selected evidence and source locators for this turn:\n" + RetrievalContent.json(initial)));
        }
        private Object pastAttempts() {
            if (focus.isEmpty()) return readHistory(new JSONObject());
            List<Requests.ChatMessage> source = history;
            String historyId = "current";
            boolean hasMore = false;
            if (input.getMessage().matches("(?is).*(上一段|上次对话|上次会话|历史对话|previous conversation|prior conversation).*")) {
                var page = recordHistory(record.getId(), "conversation", 1, 1, record.getRevision(), user);
                JSONArray entries = JSONUtil.parseArray(page.get("items"));
                if (!entries.isEmpty()) {
                    historyId = entries.getJSONObject(0).getStr("id");
                    var archived = historyMessages(record.getId(), historyId, 1, 50, record.getRevision(), user);
                    source = JSONUtil.toList(JSONUtil.parseArray(archived.get("items")), Requests.ChatMessage.class);
                    hasMore = Boolean.TRUE.equals(archived.get("hasMore"));
                }
            }
            Set<String> ids = focus.stream().map(TaskContent.Question::getId).collect(java.util.stream.Collectors.toSet());
            List<Map<String, Object>> matches = new ArrayList<>();
            for (int i = 0; i < source.size(); i++) {
                var item = source.get(i);
                if (!"user".equals(item.getRole()) || item.isPendingReview()) continue;
                var earlier = new Requests.Chat(); earlier.setMessage(item.getContent());
                if (tutor.focus(content, earlier, new TutorState()).stream().noneMatch(q -> ids.contains(q.getId()))) continue;
                matches.add(Map.of("position", i, "role", item.getRole(), "content", item.getContent()));
                if (i + 1 < source.size()) {
                    var reply = source.get(i + 1);
                    if ("assistant".equals(reply.getRole()) && !reply.isPendingReview())
                        matches.add(Map.of("position", i + 1, "role", reply.getRole(), "content", reply.getContent()));
                }
            }
            boolean earliest = input.getMessage().matches("(?is).*(最初|一开始|起初|originally|at first).*" );
            int start = earliest ? 0 : Math.max(0, matches.size() - 6);
            // 仅回查同题的少量原始问答；当前答案不能替代过去的尝试，也不将整段历史重新注入。
            return bounded(Map.of("historyId", historyId, "page", 1, "hasMore", hasMore,
                "historicalQuestionMessages", matches.subList(start, Math.min(matches.size(), start + 6)),
                "notice", "These are historical messages, not the latest saved answer. Verify the student's own words when recounting earlier attempts. Use read_history if more context is needed."));
        }
        @Override public Object read(String operation, JSONObject args) {
            validate();
            return switch (operation) {
                case "search_materials" -> search(args.getStr("query", ""), Set.of());
                case "read_material" -> readPart(args.getStr("sourceId", ""), args.getStr("partId", "s0"));
                case "read_questions" -> readQuestions(args);
                case "read_history" -> readHistory(args);
                case "read_page" -> readPage(args.getStr("materialId", ""), args.getInt("page"), args.getStr("partId", ""));
                default -> Map.of("error", "Unknown tool");
            };
        }
        Object search(String query, Set<String> excludedSources) {
            if (query.isBlank() || query.length() > 2000) return Map.of("error", "Use a short, specific search query");
            searchCalls++;
            long started = System.nanoTime();
            try {
                List<SearchScope> scopes = documents.entrySet().stream().filter(e -> !excludedSources.contains(e.getKey()))
                    .map(Map.Entry::getValue).filter(c -> !c.parts().isEmpty()).map(c -> new SearchScope(c.id(), c.revision())).toList();
                List<Map<String, Object>> hits = new ArrayList<>();
                for (SearchResult hit : qmd.searchDocuments(scopes, query, 5)) {
                    var match = documents.entrySet().stream().filter(e -> e.getValue().id().equals(hit.documentId()) && e.getValue().revision().equals(hit.revision())).findFirst();
                    if (match.isEmpty() || excludedSources.contains(match.get().getKey())) continue;
                    RetrievalDocument document = match.get().getValue();
                    DocumentPart part = document.parts().stream().filter(p -> p.id().equals(hit.partId())).findFirst().orElse(null);
                    if (part == null) continue;
                    Map<String, Object> item = source(match.get().getKey()); item.put("partId", partLocator(document, part)); item.put("page", part.page()); item.put("snippet", hit.snippet()); hits.add(item);
                }
                // 原图可用而检索文本尚未完成时，也须提供材料定位信息，不能把未命中当成没有原文件。
                return bounded(Map.of("matches", hits, "sources", sourceDirectory(), "notice", "Snippets locate evidence. Read the exact part before quoting details. Sources remain readable even when not indexed; use read_page for a requested PDF page."));
            } catch (RuntimeException exception) {
                return bounded(Map.of("matches", List.of(), "notice", "Search is unavailable. Use known questions or read authorised sources directly; do not assume missing facts.", "sources", sourceDirectory()));
            } finally { retrievalMs += java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started); }
        }
        private List<Map<String, Object>> sourceDirectory() {
            List<Map<String, Object>> result = new ArrayList<>(); result.add(source("lesson"));
            for (String id : allowed.keySet()) { if (result.size() >= 12) break; result.add(source(id)); }
            return result;
        }
        private Map<String, Object> source(String id) {
            Map<String, Object> result = new LinkedHashMap<>(); result.put("sourceId", id);
            RetrievalDocument document = documents.get(id);
            result.put("firstPart", document == null || document.parts().isEmpty() ? "" : partLocator(document, document.parts().get(0)));
            result.put("public", "lesson".equals(id) || publicSources.contains(id));
            CourseMaterial material = allowed.get(id);
            result.put("title", "lesson".equals(id) ? snapshot.getStr("title") : publicSources.contains(id) && material != null ? material.getTitle() : "Private teaching reference");
            if (material != null && PdfInputReader.isPdf(material)) result.put("pages", pdf.report(material).getUnitsTotal());
            return result;
        }
        private String partLocator(RetrievalDocument document, DocumentPart part) {
            // 对模型隐藏顺序编号，避免将 s52 等片段编号误读为 PDF 第 52 页；不改变现有索引。
            return "part-" + RetrievalContent.hash(document.id() + ":" + document.revision() + ":" + part.id()).substring(0, 16);
        }
        private boolean matchesPart(RetrievalDocument document, DocumentPart part, String locator) {
            return partLocator(document, part).equals(locator) || part.id().equals(locator);
        }
        Object readPart(String id, String partId) {
            if (!"lesson".equals(id) && !allowed.containsKey(id)) return Map.of("error", "Source is not available in this task");
            RetrievalDocument document = documents.get(id);
            if (document == null) return Map.of("source", source(id), "notice", "Search text is not prepared. Read a specific original page if needed.");
            int index = -1; for (int i = 0; i < document.parts().size(); i++) if (matchesPart(document, document.parts().get(i), partId)) { index = i; break; }
            if (index < 0) return Map.of("error", "Part not found", "source", source(id));
            DocumentPart part = document.parts().get(index); String hash = RetrievalContent.hash(part.text());
            String locator = partLocator(document, part);
            if (supplied.contains(hash)) return Map.of("sourceId", id, "partId", locator, "notice", "The identical text was already supplied in this turn");
            Map<String, Object> result = source(id); result.put("partId", locator); result.put("text", part.text()); result.put("page", part.page());
            result.put("revision", document.revision()); result.put("method", part.method()); result.put("reliable", part.reliable());
            result.put("previousPart", index > 0 ? partLocator(document, document.parts().get(index - 1)) : "");
            result.put("nextPart", index + 1 < document.parts().size() ? partLocator(document, document.parts().get(index + 1)) : "");
            Object value = bounded(result);
            if (value == result) {
                supplied.add(hash);
                state.getSources().removeIf(ref -> id.equals(ref.get("sourceId")) && (locator.equals(ref.get("partId")) || part.id().equals(ref.get("partId"))));
                state.getSources().add(Map.of("sourceId", id, "partId", locator, "page", part.page(), "revision", document.revision(), "public", "lesson".equals(id) || publicSources.contains(id)));
                while (state.getSources().size() > 8) state.getSources().remove(0);
            }
            return value;
        }
        private Object bounded(Object value) {
            int size = budget.estimate(RetrievalContent.json(value));
            int limit = properties.getTutor().getMaterialTokens();
            if (input.getMessage().matches("(?is).*(整体|全部|比较|总结|跨章节|overall|all questions|compare|summari[sz]e).*")) limit = Math.min(16000, limit * 3);
            if (readingTokens + size > limit) return Map.of("error", "This turn's reading budget is used. Answer from existing evidence or ask to narrow the scope; no source was silently truncated.");
            readingTokens += size; return value;
        }
        private Object readQuestions(JSONObject args) {
            JSONArray numbers = args.getJSONArray("numbers");
            if (numbers == null || numbers.isEmpty()) {
                String query = args.getStr("query", "").toLowerCase(Locale.ROOT);
                List<Map<String, Object>> found = new ArrayList<>();
                for (int i = 0; i < content.getQuestions().size() && found.size() < 8; i++) {
                    var question = content.getQuestions().get(i); String text = Objects.toString(question.getPrompt(), "");
                    if (query.isBlank() || text.toLowerCase(Locale.ROOT).contains(query)) found.add(Map.of("number", i + 1, "id", question.getId(), "locator", text.substring(0, Math.min(180, text.length()))));
                }
                return bounded(Map.of("questionCount", content.getQuestions().size(), "matches", found, "notice", "Read by number for full question and saved answer"));
            }
            if (numbers.size() > 8) return Map.of("error", "Read at most eight questions at a time");
            List<TaskContent.Question> selected = new ArrayList<>();
            for (Object value : numbers) {
                int number; try { number = Integer.parseInt(value.toString()); } catch (RuntimeException exception) { return Map.of("error", "Invalid question number"); }
                if (number < 1 || number > content.getQuestions().size()) return Map.of("error", "Question not found in the current task");
                var question = content.getQuestions().get(number - 1); if (!selected.contains(question)) selected.add(question);
            }
            var result = tutor.questions(content, answers, selected); Object value = bounded(result);
            if (value == result) state.setQuestionIds(selected.stream().map(TaskContent.Question::getId).toList());
            return value;
        }
        private Object readHistory(JSONObject args) {
            String historyId = args.getStr("historyId", "current");
            int pageNumber = Math.max(1, Math.min(1000000, args.getInt("page", 1)));
            boolean hasMore = false;
            if ("list".equals(historyId)) {
                var page = historyPage(record, "conversation", pageNumber, 8);
                var entries = JSONUtil.parseArray(page.get("items")).stream().map(JSONUtil::parseObj).map(item -> Map.of(
                    "id", item.getStr("id", ""), "archivedAt", item.getStr("archivedAt", ""), "messageCount", item.getInt("messageCount", 0))).toList();
                return bounded(Map.of("conversations", entries, "page", pageNumber, "hasMore", page.get("hasMore")));
            }
            List<Requests.ChatMessage> source = history;
            if (!"current".equals(historyId)) {
                var page = historyMessages(record.getId(), historyId, pageNumber, 50, record.getRevision(), user);
                source = JSONUtil.toList(JSONUtil.parseArray(page.get("items")), Requests.ChatMessage.class);
                hasMore = Boolean.TRUE.equals(page.get("hasMore"));
            }
            int before = Math.min(source.size(), Math.max(0, args.getInt("before", "current".equals(historyId) ? tutor.recentStart(history) : source.size())));
            String query = args.getStr("query", "").toLowerCase(Locale.ROOT);
            LinkedList<Map<String, Object>> found = new LinkedList<>();
            for (int i = before - 1; i >= 0 && found.size() < 6; i--) {
                var item = source.get(i);
                if (!item.isPendingReview() && (query.isBlank() || item.getContent().toLowerCase(Locale.ROOT).contains(query)))
                    found.addFirst(Map.of("position", i, "role", item.getRole(), "content", item.getContent(), "createdAt", Objects.toString(item.getCreatedAt(), "")));
            }
            return bounded(Map.of("historyId", historyId, "page", pageNumber, "hasMore", hasMore, "messages", found,
                "notice", "Use before to read earlier positions on this page; use page to read other archived messages. Historical statements may refer to superseded task content."));
        }
        private Object readPage(String id, Integer page, String partId) {
            CourseMaterial material = allowed.get(id);
            if (material == null) return Map.of("error", "Source is not available in this task");
            RetrievalDocument document = documents.get(id);
            if (!partId.isBlank()) {
                DocumentPart part = document == null ? null : document.parts().stream().filter(p -> matchesPart(document, p, partId)).findFirst().orElse(null);
                if (part == null) return Map.of("error", "Part not found in this source");
                int locatedPage = material.getMimeType().startsWith("image/") ? 1 : part.page();
                if (locatedPage < 1) return Map.of("error", "This part has no original image page");
                if (page != null && page != locatedPage) return Map.of("error", "The supplied page does not match this part", "actualPage", locatedPage);
                page = locatedPage;
            }
            if (page == null || page < 1) return Map.of("error", "Supply a partId or a known physical page number");
            int actualPage = page;
            try {
                byte[] bytes; String mime;
                if (PdfInputReader.isPdf(material)) { bytes = pdf.image(material, actualPage); mime = "image/jpeg"; }
                else if (material.getMimeType().startsWith("image/") && actualPage == 1) {
                    bytes = java.nio.file.Files.readAllBytes(properties.uploadPath(material.getStoragePath())); mime = material.getMimeType();
                } else return Map.of("error", "This source has no directly readable image page");
                var picture = javax.imageio.ImageIO.read(new java.io.ByteArrayInputStream(bytes));
                int tokens = picture == null ? 16384 : budget.imageTokens(picture.getWidth(), picture.getHeight()); if (picture != null) picture.flush();
                if (imageTokens + tokens > Math.max(properties.getTutor().getMaterialTokens(), 12000)) return Map.of("error", "Image budget reached. Read the page text or ask about one page at a time.");
                String key = "image:" + id + ":" + actualPage;
                if (!supplied.add(key)) return Map.of("notice", "This image is already available in this turn");
                imageTokens += tokens; images.add(ai.sourceImage(id, actualPage, bytes, mime));
                // 保存实际读取页，避免后续对话把片段编号或书内印刷页码误作 PDF 页码。
                state.getSources().removeIf(ref -> id.equals(ref.get("sourceId")) && "image".equals(ref.get("kind")) && Objects.equals(actualPage, ref.get("page")));
                state.getSources().add(Map.of("sourceId", id, "page", actualPage, "partId", partId, "kind", "image",
                    "revision", document == null ? RetrievalContent.sourceKey(material) : document.revision(), "public", publicSources.contains(id)));
                while (state.getSources().size() > 8) state.getSources().remove(0);
                return Map.of("source", source(id), "page", actualPage, "notice", "The original page image follows. Cite this physical page number, not the part identifier or an unverified printed page.");
            } catch (java.io.IOException exception) { return Map.of("error", "The source image is temporarily unavailable"); }
        }
        @Override public List<Message> pendingImages() { List<Message> result = new ArrayList<>(images); images.clear(); return result; }
        @Override public int imageTokens() { return imageTokens; }
    }
    @Override public Map<String,Object> approveFeedback(String id, String requestId, String text, AccountUser user) {
        LearningRecord record = getById(id); if (record == null) throw error(404, "Learning record not found");
        sessions.require(record.getSessionId(), user, true);
        if (Boolean.TRUE.equals(record.getPreview()) && !record.getUserId().equals(user.getId())) throw error(403, "Simulation access denied");
        if (text == null || text.isBlank() || text.length() > 20000) throw error(422, "Feedback text is required");
        List<Requests.ChatMessage> messages = JSONUtil.toList(record.getMessagesJson(), Requests.ChatMessage.class);
        var pending = messages.stream().filter(m -> m.isPendingReview() && requestId.equals(m.getRequestId()) && "assistant".equals(m.getRole())).findFirst().orElseThrow(() -> error(409, "This feedback is no longer awaiting review"));
        pending.setOriginalContent(pending.getContent()); pending.setReviewedBy(user.getId()); pending.setReviewedAt(Instant.now().toString());
        pending.setContent(text); pending.setPendingReview(false); record.setMessagesJson(JSONUtil.toJsonStr(messages));
        saveRevision(record, record.getRevision()); return recordView(record, true);
    }
    private void requireConversationRoom(int count) {
        if (count + 2 > properties.conversationMessageLimit())
            throw error(409, "This conversation has reached its message limit. Start a new conversation to continue; your history will be kept.");
    }
    private void appendHistory(LearningRecord record, String kind, Object payload, Integer messageCount) {
        String json = JSONUtil.toJsonStr(payload);
        if (json.getBytes(StandardCharsets.UTF_8).length > 1024 * 1024)
            log.warn("Large learning history entry: record={}, kind={}, bytes={}", record.getId(), kind, json.getBytes(StandardCharsets.UTF_8).length);
        LearningRecordHistory entry = new LearningRecordHistory();
        entry.setRecordId(record.getId()); entry.setKind(kind); entry.setPayloadJson(json); entry.setMessageCount(messageCount);
        entry.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC)); histories.insert(entry);
    }
    private JSONArray legacyHistory(LearningRecord record, String kind) {
        String json = "answer".equals(kind) ? record.getAnswerHistoryJson() : record.getConversationHistoryJson();
        return json == null || json.isBlank() ? new JSONArray() : JSONUtil.parseArray(json);
    }
    private LearningRecord readableRecord(String id, Long revision, AccountUser user) {
        LearningRecord record = getById(id);
        if (record == null) throw error(404, "Learning record not found");
        if (user.getId().equals(record.getUserId())) record = owned(id, user, false);
        else {
            sessions.require(record.getSessionId(), user, true);
            if (Boolean.TRUE.equals(record.getPreview())) throw error(403, "Simulation access denied");
        }
        if (revision != null && !revision.equals(record.getRevision())) throw error(409, "Learning record changed. Reload before saving.");
        return record;
    }
    private int pageSize(int page, int size, int maximum) {
        if (page < 1 || page > 1000000 || size < 1) throw error(422, "Invalid history page");
        return Math.min(size, maximum);
    }
    private Map<String, Object> pageResult(List<?> items, long total, int page, int size, long revision) {
        return Map.of("items", items, "total", total, "page", page, "size", size,
            "hasMore", (long) page * size < total, "revision", revision);
    }
    private Map<String, Object> historyPage(LearningRecord record, String kind, int page, int size) {
        size = pageSize(page, size, "answer".equals(kind) ? properties.answerPageLimit() : properties.conversationPageLimit());
        List<LearningRecord> sources = relatedRecords(record);
        Map<String, LearningRecord> sourcesById = new HashMap<>(); sources.forEach(source -> sourcesById.put(source.getId(), source));
        List<String> recordIds = new ArrayList<>(sourcesById.keySet());
        List<Map<String, Object>> legacy = new ArrayList<>();
        if ("answer".equals(kind)) {
            JSONObject earlier = JSONUtil.parseObj(record.getAnswersJson()), current = currentAnswers(record);
            current.keySet().forEach(earlier::remove);
            if (!earlier.isEmpty()) legacy.add(new LinkedHashMap<>(Map.of("id", "record-answer-" + record.getId(),
                "savedAt", Objects.toString(record.getUpdatedAt(), ""), "answers", earlier, "questions", historyQuestions(record))));
        }
        for (LearningRecord source : sources) {
            if (!source.getId().equals(record.getId())) {
                if ("answer".equals(kind)) {
                    List<Map<String, Object>> files = materials.lambdaQuery().eq(CourseMaterial::getRecordId, source.getId())
                        .eq(CourseMaterial::getArchived, false).select(CourseMaterial::getId, CourseMaterial::getTitle).list().stream()
                        .map(file -> Map.<String, Object>of("id", file.getId(), "title", file.getTitle())).toList();
                    JSONObject answers = JSONUtil.parseObj(source.getAnswersJson());
                    if (!answers.isEmpty() || !files.isEmpty()) legacy.add(new LinkedHashMap<>(Map.of(
                        "id", "record-answer-" + source.getId(), "savedAt", Objects.toString(source.getUpdatedAt(), ""),
                        "answers", answers, "questions", historyQuestions(source), "attachments", files)));
                } else {
                    JSONArray messages = JSONUtil.parseArray(source.getMessagesJson());
                    if (!messages.isEmpty()) legacy.add(new LinkedHashMap<>(Map.of("id", "record-conversation-" + source.getId(),
                        "archivedAt", Objects.toString(source.getUpdatedAt(), ""), "messageCount", messages.size())));
                }
            }
            JSONArray previous = legacyHistory(source, kind);
            for (int index = previous.size() - 1; index >= 0; index--) {
                JSONObject entry = previous.getJSONObject(index);
                Map<String, Object> item = "answer".equals(kind) ? new LinkedHashMap<>(entry) : new LinkedHashMap<>();
                item.put("id", "legacy-" + kind + "-" + source.getId() + "-" + index);
                if ("answer".equals(kind)) item.putIfAbsent("questions", historyQuestions(source));
                else {
                    item.put("archivedAt", entry.getStr("archivedAt", ""));
                    item.put("messageCount", entry.getJSONArray("messages") == null ? 0 : entry.getJSONArray("messages").size());
                }
                legacy.add(item);
            }
        }
        long storedCount = histories.selectCount(Wrappers.<LearningRecordHistory>lambdaQuery()
            .in(LearningRecordHistory::getRecordId, recordIds).eq(LearningRecordHistory::getKind, kind));
        long offset = (long) (page - 1) * size;
        List<Map<String, Object>> items = new ArrayList<>();
        if (offset < storedCount) {
            var query = Wrappers.<LearningRecordHistory>lambdaQuery().in(LearningRecordHistory::getRecordId, recordIds)
                .eq(LearningRecordHistory::getKind, kind).orderByDesc(LearningRecordHistory::getId);
            if ("conversation".equals(kind)) query.select(LearningRecordHistory::getId, LearningRecordHistory::getRecordId, LearningRecordHistory::getCreatedAt, LearningRecordHistory::getMessageCount);
            for (LearningRecordHistory entry : histories.selectPage(new Page<LearningRecordHistory>(page, size, false), query).getRecords()) {
                Map<String, Object> item = "answer".equals(kind) ? new LinkedHashMap<>(JSONUtil.parseObj(entry.getPayloadJson())) : new LinkedHashMap<>();
                item.put("id", entry.getId().toString());
                if ("answer".equals(kind)) item.putIfAbsent("questions", historyQuestions(sourcesById.get(entry.getRecordId())));
                if ("conversation".equals(kind)) {
                    item.put("archivedAt", entry.getCreatedAt().toInstant(ZoneOffset.UTC).toString());
                    item.put("messageCount", Objects.requireNonNullElse(entry.getMessageCount(), 0));
                }
                items.add(item);
            }
        }
        for (long index = Math.max(0, offset - storedCount); index < legacy.size() && items.size() < size; index++) {
            items.add(legacy.get((int) index));
        }
        return pageResult(items, storedCount + legacy.size(), page, size, record.getRevision());
    }
    @Override public Map<String, Object> recordHistory(String id, String kind, int page, int size, Long revision, AccountUser user) {
        LearningRecord record = readableRecord(id, revision, user);
        if ("attachment".equals(kind)) {
            sessions.require(record.getSessionId(), user, true);
            size = pageSize(page, size, 50);
            var result = materials.lambdaQuery().in(CourseMaterial::getRecordId, relatedRecords(record).stream().map(LearningRecord::getId).toList()).eq(CourseMaterial::getArchived, true)
                .isNotNull(CourseMaterial::getOwnerId).orderByDesc(CourseMaterial::getFileRemovedAt).orderByDesc(CourseMaterial::getId)
                .page(new Page<CourseMaterial>(page, size));
            List<String> actorIds = result.getRecords().stream().map(CourseMaterial::getRemovedBy).filter(Objects::nonNull).distinct().toList();
            Map<String, String> names = new HashMap<>();
            if (!actorIds.isEmpty()) accounts.listByIds(actorIds).forEach(actor -> names.put(actor.getId(), actor.getName()));
            List<Map<String, Object>> entries = result.getRecords().stream().map(file -> Map.<String, Object>of(
                "id", file.getId(), "title", file.getTitle(), "removedAt", Objects.toString(file.getFileRemovedAt(), ""),
                "removedBy", names.getOrDefault(file.getRemovedBy(), Objects.toString(file.getRemovedBy(), "")),
                "recycled", file.getTrashPath() != null, "fileSize", Objects.requireNonNullElse(file.getFileSize(), 0L))).toList();
            return pageResult(entries, result.getTotal(), page, size, record.getRevision());
        }
        if (!Set.of("answer", "conversation").contains(kind)) throw error(422, "Invalid history kind");
        return historyPage(record, kind, page, size);
    }
    @Override public Map<String, Object> historyMessages(String id, String historyId, int page, int size, Long revision, AccountUser user) {
        LearningRecord record = readableRecord(id, revision, user);
        size = pageSize(page, size, 50);
        Map<String, LearningRecord> sources = new HashMap<>(); relatedRecords(record).forEach(source -> sources.put(source.getId(), source));
        LearningRecord source = record;
        JSONArray messages;
        if ("current".equals(historyId)) messages = JSONUtil.parseArray(record.getMessagesJson());
        else if (historyId.startsWith("record-conversation-")) {
            source = sources.get(historyId.substring("record-conversation-".length()));
            if (source == null) throw error(404, "History entry not found");
            messages = JSONUtil.parseArray(source.getMessagesJson());
        }
        else if (historyId.matches("legacy-conversation-\\d+")) {
            JSONArray legacy = legacyHistory(record, "conversation");
            int index;
            try { index = Integer.parseInt(historyId.substring("legacy-conversation-".length())); }
            catch (NumberFormatException exception) { throw error(404, "History entry not found"); }
            if (index >= legacy.size()) throw error(404, "History entry not found");
            messages = legacy.getJSONObject(index).getJSONArray("messages");
        } else if (historyId.startsWith("legacy-conversation-")) {
            int separator = historyId.lastIndexOf('-');
            if (separator < "legacy-conversation-".length()) throw error(404, "History entry not found");
            source = sources.get(historyId.substring("legacy-conversation-".length(), separator));
            if (source == null) throw error(404, "History entry not found");
            int index;
            try { index = Integer.parseInt(historyId.substring(separator + 1)); }
            catch (NumberFormatException exception) { throw error(404, "History entry not found"); }
            JSONArray legacy = legacyHistory(source, "conversation");
            if (index < 0 || index >= legacy.size()) throw error(404, "History entry not found");
            messages = legacy.getJSONObject(index).getJSONArray("messages");
        } else {
            long historyKey;
            try { historyKey = Long.parseLong(historyId); }
            catch (NumberFormatException exception) { throw error(404, "History entry not found"); }
            LearningRecordHistory entry = histories.selectOne(Wrappers.<LearningRecordHistory>lambdaQuery()
                .eq(LearningRecordHistory::getId, historyKey).in(LearningRecordHistory::getRecordId, sources.keySet()).eq(LearningRecordHistory::getKind, "conversation"));
            if (entry == null) throw error(404, "History entry not found");
            source = sources.get(entry.getRecordId());
            messages = JSONUtil.parseObj(entry.getPayloadJson()).getJSONArray("messages");
        }
        if (messages == null) messages = new JSONArray();
        int start = (int) Math.min((long) (page - 1) * size, messages.size());
        JSONArray visible = JSONUtil.parseArray(messages.subList(start, Math.min(start + size, messages.size())));
        if ("student".equals(user.getRole())) filterPrivateFeedback(visible);
        Map<String, Object> result = new LinkedHashMap<>(pageResult(visible, messages.size(), page, size, record.getRevision()));
        result.put("removedAttachments", removedAttachments(source, visible));
        return result;
    }
    private Map<String, String> removedAttachments(LearningRecord record, JSONArray messages) {
        Set<String> ids = new HashSet<>();
        messages.forEach(item -> {
            JSONArray references = ((JSONObject) item).getJSONArray("attachmentIds");
            if (references != null) references.forEach(value -> ids.add(Objects.toString(value)));
        });
        Map<String, String> removed = new LinkedHashMap<>();
        if (!ids.isEmpty()) materials.lambdaQuery().eq(CourseMaterial::getRecordId, record.getId()).eq(CourseMaterial::getOwnerId, record.getUserId())
            .eq(CourseMaterial::getArchived, true).in(CourseMaterial::getId, ids).list().forEach(file -> removed.put(file.getId(), file.getTitle()));
        return removed;
    }
    private void filterPrivateFeedback(JSONArray messages) {
        if(messages == null) return;
        messages.forEach(item -> {JSONObject message=(JSONObject)item; message.remove("originalContent"); message.remove("reviewedBy"); if(message.getBool("pendingReview",false))message.set("content","");});
    }
    @Override public Map<String, Object> view(LearningRecord record) { return recordView(record, false); }
    private Map<String, Object> recordView(LearningRecord record, boolean teacher) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", record.getId()); result.put("sessionId", record.getSessionId()); result.put("versionId", record.getVersionId()); result.put("userId", record.getUserId());
        result.put("status", record.getStatus()); result.put("revision", record.getRevision()); result.put("answers", currentAnswers(record));
        JSONArray allMessages = JSONUtil.parseArray(record.getMessagesJson());
        int limit = properties.conversationMessageLimit();
        JSONArray messages = JSONUtil.parseArray(allMessages.subList(Math.max(0, allMessages.size() - limit), allMessages.size()));
        if (!teacher) filterPrivateFeedback(messages);
        Map<String, Object> answers = historyPage(record, "answer", 1, 5);
        Map<String, Object> conversations = historyPage(record, "conversation", 1, 3);
        result.put("answerHistory", answers.get("items")); result.put("conversationHistory", conversations.get("items"));
        result.put("answerHistoryCount", answers.get("total")); result.put("conversationHistoryCount", conversations.get("total"));
        result.put("historyTruncated", Boolean.TRUE.equals(answers.get("hasMore")) || Boolean.TRUE.equals(conversations.get("hasMore")));
        result.put("messageCount", allMessages.size()); result.put("messageLimit", limit);
        result.put("messagesTruncated", allMessages.size() > messages.size());
        result.put("conversationLimitReached", allMessages.size() + 2 > limit);
        result.put("attachmentMaxBytes", properties.getAttachmentMaxBytes());
        result.put("preview", Boolean.TRUE.equals(record.getPreview())); result.put("messages", messages); result.put("teacherNote", record.getTeacherNote());
        result.put("removedAttachments", removedAttachments(record, messages));
        result.put("updatedAt", record.getUpdatedAt()); result.put("submittedAt", record.getSubmittedAt()); result.put("reviewedAt", record.getReviewedAt()); return result;
    }
}
