package zzm.service.impl;

import zzm.dto.*;
import zzm.entity.*;
import zzm.mapper.*;
import zzm.service.*;
import cn.hutool.core.util.IdUtil;
import cn.hutool.json.*;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.*;
import java.util.*;
import static zzm.exception.ApiErrors.error;

@Service
@RequiredArgsConstructor
public class SessionServiceImpl extends ServiceImpl<TeachingSessionMapper, TeachingSession> implements SessionService {
    private final CourseService courses;
    private final MaterialService materials;
    private final SessionVersionMapper versionMapper;
    private final LearningRecordMapper records;

    @Override public TeachingSession require(String id, AccountUser user, boolean teacher) {
        TeachingSession session = getById(id);
        if (session == null) throw error(404, "Task not found");
        courses.requireAccess(session.getCourseId(), user, teacher);
        return session;
    }
    @Override public List<Map<String, Object>> listCourse(String courseId, AccountUser user) {
        boolean teacher = !"student".equals(user.getRole()); courses.requireAccess(courseId, user, teacher);
        List<TeachingSession> sessions = lambdaQuery().eq(TeachingSession::getCourseId, courseId).orderByAsc(TeachingSession::getTitle).list();
        if (teacher) return sessions.stream().map(s -> {
            Map<String, Object> value = new LinkedHashMap<>();
            value.put("id", s.getId()); value.put("courseId", s.getCourseId()); value.put("title", s.getTitle());
            value.put("description", s.getDescription()); value.put("sessionType", s.getSessionType());
            value.put("archived", s.getArchived()); value.put("publishedVersionId", s.getPublishedVersionId()); value.put("revision", s.getRevision());
            return value;
        }).toList();
        List<String> ids = sessions.stream().filter(s -> !Boolean.TRUE.equals(s.getArchived())).map(TeachingSession::getPublishedVersionId).filter(Objects::nonNull).toList();
        if (ids.isEmpty()) return List.of();
        return versionMapper.selectByIds(ids).stream().map(v -> studentProjection(JSONUtil.parseObj(v.getContentJson()))).toList();
    }
    @Override @Transactional public TeachingSession create(String courseId, Requests.SessionInput input, AccountUser user) {
        Course course = courses.requireAccess(courseId, user, true);
        if (Boolean.TRUE.equals(course.getArchived())) throw error(409, "Restore the course before creating tasks");
        TeachingSession session = new TeachingSession(); session.setCourseId(courseId); session.setRevision(0L); session.setArchived(false);
        fill(session, input); save(session); return session;
    }
    @Override @Transactional public TeachingSession copy(String id, String courseId, AccountUser user) {
        TeachingSession original = require(id, user, true); courses.requireAccess(courseId, user, true);
        Requests.SessionInput input = JSONUtil.toBean(JSONUtil.toJsonStr(view(original, true)), Requests.SessionInput.class);
        Map<String,String> replacements = new HashMap<>();
        for (CourseMaterial source : materials.selected(original.getCourseId(), input.getMaterialIds())) {
            if (courseId.equals(original.getCourseId())) { replacements.put(source.getId(), source.getId()); continue; }
            CourseMaterial material = JSONUtil.toBean(JSONUtil.toJsonStr(source), CourseMaterial.class);
            material.setId(IdUtil.fastSimpleUUID()); material.setCourseId(courseId); material.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC));
            materials.save(material); replacements.put(source.getId(), material.getId());
        }
        input.setMaterialIds(input.getMaterialIds().stream().map(replacements::get).toList());
        for (var question : input.getContent().getQuestions()) {
            question.setId(IdUtil.fastSimpleUUID());
            question.setSourceMaterialIds(question.getSourceMaterialIds().stream().map(replacements::get).toList());
            question.setImageMaterialIds(question.getImageMaterialIds().stream().map(replacements::get).toList());
        }
        input.getContent().setIllustrationMaterialIds(input.getContent().getIllustrationMaterialIds().stream().map(replacements::get).toList());
        TeachingSession result = create(courseId, input, user);
        // Copies are fresh drafts; published versions, student records and simulations are never copied.
        return result;
    }
    @Override @Transactional public TeachingSession edit(String id, Requests.SessionInput input, AccountUser user) {
        TeachingSession session = require(id, user, true);
        if (!session.getRevision().equals(input.getRevision())) throw error(409, "Task changed. Reload before saving.");
        fill(session, input);
        if (!updateById(session)) throw error(409, "Task changed. Reload before saving.");
        return session;
    }
    private void fill(TeachingSession session, Requests.SessionInput input) {
        materials.selected(session.getCourseId(), input.getMaterialIds());
        TaskContent content = validateContent(input.getContent(), input.getMaterialIds(), false);
        // AI strategy is generated by the server, never taken from teacher form fields.
        content.setAiConfig(session.getContentJson() == null ? new TaskContent.AiConfig() : JSONUtil.toBean(session.getContentJson(), TaskContent.class).getAiConfig());
        if (!input.getLearningGoals().isBlank()) content.setLearningGoals(input.getLearningGoals().lines().filter(s -> !s.isBlank()).toList());
        session.setTitle(input.getTitle().trim()); session.setDescription(input.getDescription()); session.setSessionType(input.getSessionType());
        session.setTopic(input.getTopic()); session.setLearningGoals(input.getLearningGoals()); session.setAdditionalInstructions(input.getAdditionalInstructions());
        session.setTeachingLanguage(input.getTeachingLanguage()); session.setMaterialIdsJson(JSONUtil.toJsonStr(input.getMaterialIds())); session.setContentJson(JSONUtil.toJsonStr(content));
    }
    @Override public Map<String, Object> view(TeachingSession session, boolean teacher) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", session.getId()); result.put("courseId", session.getCourseId()); result.put("title", session.getTitle());
        result.put("description", session.getDescription()); result.put("sessionType", session.getSessionType()); result.put("topic", session.getTopic());
        result.put("learningGoals", session.getLearningGoals()); result.put("additionalInstructions", session.getAdditionalInstructions());
        result.put("teachingLanguage", session.getTeachingLanguage()); result.put("revision", session.getRevision());
        result.put("publishedVersionId", session.getPublishedVersionId()); result.put("archived", session.getArchived());
        List<String> ids = JSONUtil.toList(session.getMaterialIdsJson(), String.class);
        result.put("materialIds", ids); result.put("content", JSONUtil.toBean(session.getContentJson(), TaskContent.class));
        result.put("materials", ids.isEmpty() ? List.of() : materials.listByIds(ids).stream().map(materials::view).toList());
        Course course = courses.getById(session.getCourseId()); result.put("courseInstructions", course.getSystemInstructions()); result.put("courseInformation", Objects.toString(course.getCourseInformation(), "")); result.put("studentProfile", Objects.toString(course.getStudentProfile(), ""));
        return teacher ? result : studentProjection(result);
    }
    @Override public SessionVersion version(String sessionId, String versionId) {
        SessionVersion version = versionMapper.selectById(versionId);
        if (version == null || !version.getSessionId().equals(sessionId)) throw error(404, "Task version not found");
        return version;
    }
    @Override public Map<String, Object> published(String id, String versionId, AccountUser user) {
        TeachingSession session = require(id, user, false);
        String selected = versionId == null || versionId.isBlank() ? session.getPublishedVersionId() : versionId;
        if (selected == null) throw error(404, "Task is not published");
        if ("student".equals(user.getRole()) && (Boolean.TRUE.equals(session.getArchived()) || !selected.equals(session.getPublishedVersionId()))) {
            if (records.selectCount(Wrappers.<LearningRecord>lambdaQuery().eq(LearningRecord::getSessionId, id).eq(LearningRecord::getUserId, user.getId()).eq(LearningRecord::getVersionId, selected)) == 0) throw error(403, "Task version access denied");
        }
        return studentProjection(JSONUtil.parseObj(version(id, selected).getContentJson()));
    }
    @Override @Transactional public SessionVersion publish(String id, long revision, AccountUser user) {
        TeachingSession session = require(id, user, true);
        if (Boolean.TRUE.equals(session.getArchived()) || Boolean.TRUE.equals(courses.getById(session.getCourseId()).getArchived())) throw error(409, "Restore the course and task before publishing");
        if (session.getRevision() != revision) throw error(409, "Task changed. Reload before publishing.");
        List<String> ids = JSONUtil.toList(session.getMaterialIdsJson(), String.class);
        List<CourseMaterial> selected = materials.selected(session.getCourseId(), ids);
        materials.requireProcessed(selected);
        TaskContent content = validateContent(JSONUtil.toBean(session.getContentJson(), TaskContent.class), ids, true);
        if ("assignment".equals(session.getSessionType()) && content.getQuestions().isEmpty()) throw error(422, "An assignment must contain questions");
        SessionVersion version = new SessionVersion(); version.setId(IdUtil.fastSimpleUUID()); version.setSessionId(id);
        version.setCourseId(session.getCourseId()); version.setRevision(revision + 1); version.setLabel("V" + (revision + 1)); version.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC));
        session.setPublishedVersionId(version.getId());
        if (!updateById(session)) throw error(409, "Task changed. Reload before publishing.");
        Map<String, Object> snapshot = view(session, true); snapshot.put("versionId", version.getId());
        version.setContentJson(JSONUtil.toJsonStr(snapshot)); versionMapper.insert(version); return version;
    }
    @Override @Transactional public void restore(String id, String versionId, long revision, AccountUser user) {
        TeachingSession current = require(id, user, true);
        if (current.getRevision() != revision) throw error(409, "Task changed. Reload before restoring.");
        JSONObject snapshot = JSONUtil.parseObj(version(id, versionId).getContentJson());
        Requests.SessionInput input = snapshot.toBean(Requests.SessionInput.class); input.setRevision(revision);
        // Restore the saved AI strategy as well as student-facing content, without publishing.
        current.setContentJson(JSONUtil.toJsonStr(input.getContent())); fill(current, input);
        if (!updateById(current)) throw error(409, "Task changed. Reload before restoring.");
    }
    @Override public void archive(String id, boolean archived, AccountUser user) {
        TeachingSession session = require(id, user, true); session.setArchived(archived);
        if (!updateById(session)) throw error(409, "Task changed. Reload before saving.");
    }
    @Override public List<Map<String, Object>> versions(String id, AccountUser user) {
        require(id, user, true);
        return versionMapper.selectList(Wrappers.<SessionVersion>lambdaQuery().eq(SessionVersion::getSessionId, id).orderByDesc(SessionVersion::getRevision))
            .stream().map(v -> Map.<String, Object>of("id", v.getId(), "revision", v.getRevision(), "label", v.getLabel(), "createdAt", v.getCreatedAt())).toList();
    }
    @Override public TaskContent validateContent(TaskContent content, List<String> materialIds, boolean publishing) {
        if (content == null || content.getQuestions() == null || content.getLearningGoals() == null || content.getLearningPlan() == null) throw error(422, "Task content is incomplete");
        if (content.getQuestions().size() > 100 || content.getLearningPlan().size() > 30 || content.getLearningGoals().size() > 30) throw error(422, "Task content exceeds the size limit");
        if (content.getHandout() == null) content.setHandout("");
        if (content.getOpeningMessage() == null) content.setOpeningMessage("");
        if (content.getRubric() == null) content.setRubric("");
        if (content.getHandout().length() > 180000 || content.getOpeningMessage().length() > 20000 || content.getRubric().length() > 20000) throw error(422, "Task content exceeds the size limit");
        if (!Set.of("guided", "autonomous").contains(content.getTeachingMode()) || !Set.of("immediate", "teacherReview").contains(content.getFeedbackMode())) throw error(422, "Invalid teaching or feedback mode");
        if (content.getDiagrams() == null) content.setDiagrams(new ArrayList<>());
        if (content.getDiagrams().size() > 10) throw error(422, "Too many diagrams");
        for (var diagram : content.getDiagrams()) {
            if (diagram == null || diagram.getNodes() == null || diagram.getEdges() == null || diagram.getNodes().size() > 80 || diagram.getEdges().size() > 160) throw error(422, "Invalid diagram");
            if (diagram.getId() == null || diagram.getId().isBlank()) diagram.setId(IdUtil.fastSimpleUUID());
            if (diagram.getTitle() == null) diagram.setTitle("");
            if (diagram.getTitle().length() > 300) throw error(422, "Invalid diagram");
            Set<String> nodeIds = new HashSet<>();
            for (var node : diagram.getNodes()) {
                if (node == null || node.getId() == null || !nodeIds.add(node.getId()) || node.getText() == null || node.getText().length() > 2000 || node.getX() == null || node.getY() == null || node.getX() < 0 || node.getY() < 0 || node.getX() > 4000 || node.getY() > 4000) throw error(422, "Invalid diagram node");
            }
            for (var edge : diagram.getEdges()) if (edge == null || !nodeIds.contains(edge.getFrom()) || !nodeIds.contains(edge.getTo())) throw error(422, "Invalid diagram connection");
        }
        Set<String> seen = new HashSet<>();
        Set<String> publicImages = new HashSet<>();
        if (!materialIds.isEmpty()) materials.listByIds(materialIds).stream()
            .filter(m -> "student".equals(m.getVisibility()) && m.getMimeType().startsWith("image/"))
            .forEach(m -> publicImages.add(m.getId()));
        if (content.getIllustrationMaterialIds() == null) content.setIllustrationMaterialIds(new ArrayList<>());
        if (!publicImages.containsAll(content.getIllustrationMaterialIds())) throw error(422, "Lesson illustrations must be selected images visible to students");
        int questionNumber = 0;
        for (TaskContent.Question question : content.getQuestions()) {
            questionNumber++;
            if (question == null) throw error(422, "Question data is incomplete");
            if (question.getId() == null || question.getId().isBlank()) question.setId(IdUtil.fastSimpleUUID());
            if (question.getId().length() > 100 || !seen.add(question.getId())) throw error(422, "Question identifiers must be unique");
            if (!Set.of("openResponse", "readingResponse", "fillInBlank", "singleChoice", "multipleChoice", "trueFalse", "imageMatching").contains(Objects.toString(question.getType(), ""))) throw error(422, "Unsupported question type");
            if (question.getPrompt() == null || question.getPrompt().length() > 20000 || publishing && question.getPrompt().isBlank()) throw error(422, "Question text is required");
            if ("openResponse".equals(question.getType()) && question.getOptions() == null) question.setOptions(List.of());
            if (question.getOptions() == null || question.getOptions().size() > 20 || question.getOptions().stream().anyMatch(option -> option == null || option.length() > 10000)) throw error(422, "Question " + questionNumber + ": Invalid answer options");
            if (question.getSourceMaterialIds() == null) question.setSourceMaterialIds(new ArrayList<>());
            if (question.getImageMaterialIds() == null) question.setImageMaterialIds(new ArrayList<>());
            if (!materialIds.containsAll(question.getSourceMaterialIds()) || !materialIds.containsAll(question.getImageMaterialIds())) throw error(422, "Question references must use selected materials");
            if (!publicImages.containsAll(question.getImageMaterialIds())) throw error(422, "Question illustrations must be images visible to students");
            if (publishing) {

                if (Set.of("singleChoice", "multipleChoice", "trueFalse").contains(question.getType())) {
                    if (question.getOptions().size() < 2 || question.getOptions().stream().anyMatch(String::isBlank) || new HashSet<>(question.getOptions()).size() != question.getOptions().size()) throw error(422, "Choice questions need distinct non-empty options");
                    String reference = Objects.toString(question.getReferenceAnswer(), "");
                    List<String> answers = reference.isBlank() ? List.of() : "multipleChoice".equals(question.getType())
                        ? TaskContent.multipleChoiceAnswers(reference, question.getOptions()) : List.of(reference);
                    if (!question.getOptions().containsAll(answers)) throw error(422, "Question " + questionNumber + ": The correct answer must match an option");
                }
                if ("fillInBlank".equals(question.getType()) && (question.getAnswerSlots() == null || question.getAnswerSlots() < 1 || question.getAnswerSlots() > 20)) throw error(422, "Invalid number of blanks");
                if ("imageMatching".equals(question.getType()) && question.getImageMaterialIds().isEmpty()) throw error(422, "Image matching questions need illustrations");
            }
        }
        if (publishing && !"autonomous".equals(content.getTeachingMode()) && (content.getLearningGoals().isEmpty() || content.getLearningPlan().isEmpty())) throw error(422, "Generate learning goals and a teaching plan before publishing");
        if (content.getLearningGoals().stream().anyMatch(g -> g == null || g.isBlank() || g.length() > 10000)
            || content.getLearningPlan().stream().anyMatch(step -> step == null || step.getTitle() == null || step.getTitle().isBlank() || step.getDescription() == null)) throw error(422, "Learning goals and plan steps must contain meaningful text");
        if (content.getAiConfig() == null) content.setAiConfig(new TaskContent.AiConfig());
        TaskContent.AiConfig config = content.getAiConfig();
        if (config.getTeachingApproach() == null || config.getTeachingApproach().isBlank()) config.setTeachingApproach("Follow the teacher's instructions and adapt to the learner's responses.");
        if (config.getFeedbackStrategy() == null || config.getFeedbackStrategy().isBlank()) config.setFeedbackStrategy("Give constructive formative feedback; use the supplied rubric when available.");
        if (config.getResponseDetail() == null || config.getResponseDetail().isBlank()) config.setResponseDetail("Match the learner's needs.");
        if (config.getTone() == null || config.getTone().isBlank()) config.setTone("Clear, supportive and precise.");
        return content;
    }
    @Override public Map<String, Object> studentProjection(Map<String, Object> snapshot) {
        JSONObject result = JSONUtil.parseObj(JSONUtil.toJsonStr(snapshot));
        for (String key : List.of("additionalInstructions", "courseInstructions", "courseInformation", "studentProfile")) result.remove(key);
        JSONObject content = result.getJSONObject("content");
        if (content != null) {
            content.remove("aiConfig"); content.remove("rubric");
            JSONArray questions = content.getJSONArray("questions");
            if (questions != null) questions.forEach(value -> { JSONObject q = (JSONObject) value; q.remove("referenceAnswer"); q.remove("explanation"); });
        }
        JSONArray source = result.getJSONArray("materials");
        List<JSONObject> visible = source == null ? List.of() : source.stream().map(JSONUtil::parseObj).filter(m -> "student".equals(m.getStr("visibility"))).toList();
        result.set("materials", visible); result.set("materialIds", visible.stream().map(m -> m.getStr("id")).toList());
        return result;
    }
}
