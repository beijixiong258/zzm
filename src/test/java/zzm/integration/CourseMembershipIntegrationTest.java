package zzm.integration;

import cn.hutool.json.JSONUtil;
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.mybatis.spring.annotation.MapperScan;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.config.YamlPropertiesFactoryBean;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.core.io.FileSystemResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;
import zzm.config.*;
import zzm.controller.*;
import zzm.dto.*;
import zzm.entity.*;
import zzm.mapper.*;
import zzm.service.*;
import zzm.service.impl.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** 连接本机测试库的破坏性集成测试；必须显式开启，运行前后清空业务数据并回收测试附件。 */
@EnabledIfSystemProperty(named = "zzm.test.database.enabled", matches = "true")
@SpringBootTest(classes = CourseMembershipIntegrationTest.TestApplication.class, properties = {
    "spring.sql.init.mode=never", "spring.main.banner-mode=off", "logging.level.root=WARN",
    "app.demo-enabled=false", "app.retrieval.enabled=false", "spring.datasource.hikari.maximum-pool-size=12"
})
@AutoConfigureMockMvc
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class CourseMembershipIntegrationTest {
    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableConfigurationProperties(AppProperties.class)
    @MapperScan("zzm.mapper")
    @Import({WebConfig.class, JsonConfig.class, CourseAccess.class, CourseController.class,
        SessionController.class, LearningController.class, MaterialController.class, ApiExceptionHandler.class,
        CourseServiceImpl.class, AccountServiceImpl.class, MaterialServiceImpl.class,
        SessionServiceImpl.class, LearningServiceImpl.class, LearningAssessmentServiceImpl.class,
        TaskExporter.class, ContextBudget.class, TutorContext.class})
    static class TestApplication {}

    private static final List<String> TABLES = List.of("learning_assessment", "learning_record_history", "learning_record", "generation_job",
        "session_version", "teaching_session", "course_member", "course_material", "course", "auth_session", "legacy_record", "account_user");
    private static final String TEST_SCHEMA = System.getProperty("zzm.test.schema", "zzm");
    private static final Path TEST_DIRECTORY = Path.of(System.getProperty("zzm.test.directory", System.getProperty("java.io.tmpdir") + "/zzm-membership-tests"));
    private static final Path RECYCLE_DIRECTORY = Path.of(System.getProperty("zzm.test.recycle-root", System.getProperty("java.io.tmpdir") + "/zzm-membership-recycle"));

    @DynamicPropertySource static void configureDatabase(DynamicPropertyRegistry registry) {
        if (!"true".equals(System.getProperty("zzm.test.allow-clean")))
            throw new IllegalStateException("必须显式授权清库后才能启动本机数据库集成测试。");
        YamlPropertiesFactoryBean yaml = new YamlPropertiesFactoryBean();
        yaml.setResources(new FileSystemResource(Objects.requireNonNull(System.getProperty("zzm.test.config"))));
        Properties config = Objects.requireNonNull(yaml.getObject());
        String configuredUrl = Objects.requireNonNull(config.getProperty("spring.datasource.url"));
        if (!configuredUrl.matches("jdbc:mysql://(mysql|localhost|127\\.0\\.0\\.1):3306/zzm(?:\\?.*)?"))
            throw new IllegalStateException("集成测试只允许连接本机 zzm 数据库。");
        if (!TEST_SCHEMA.matches("zzm|zzm_test_[0-9a-f]{12}"))
            throw new IllegalStateException("测试库名称必须是 zzm 或本次创建的隔离测试库。");
        String url = configuredUrl.replaceFirst("jdbc:mysql://[^/]+/zzm", "jdbc:mysql://127.0.0.1:3306/" + TEST_SCHEMA);
        registry.add("spring.datasource.url", () -> url);
        registry.add("spring.datasource.username", () -> config.getProperty("spring.datasource.username"));
        registry.add("spring.datasource.password", () -> config.getProperty("spring.datasource.password"));
        registry.add("app.upload-dir", () -> TEST_DIRECTORY.resolve("uploads").toString());
        registry.add("app.trash-dir", RECYCLE_DIRECTORY::toString);
    }

    @MockitoBean AiService ai;
    @MockitoBean DocumentParser parser;
    @MockitoBean PdfInputReader pdf;
    @MockitoBean QmdClient qmd;
    @Autowired MockMvc http;
    @Autowired JdbcTemplate jdbc;
    @Autowired CourseService courses;
    @Autowired SessionService sessions;
    @Autowired LearningService learning;
    @Autowired LearningAssessmentService assessments;
    @Autowired MaterialService materials;
    @Autowired AccountUserMapper accounts;
    @Autowired AuthSessionMapper authSessions;
    @Autowired CourseMemberMapper members;
    @Autowired LearningRecordMapper records;
    @Autowired LearningRecordHistoryMapper histories;
    @Autowired GenerationJobMapper jobs;
    @Autowired SessionVersionMapper versions;
    @Autowired AppProperties properties;
    @Autowired PlatformTransactionManager transactionManager;

    AccountUser teacher, otherTeacher, student, otherStudent;
    Course course, otherCourse;

    @BeforeAll void checkDatabaseAndCleanExistingTestData() throws Exception {
        assertEquals("true", System.getProperty("zzm.test.allow-clean"), "清库必须单独显式授权。");
        assertEquals(TEST_SCHEMA, jdbc.queryForObject("SELECT DATABASE()", String.class));
        System.out.println("测试前业务表行数：" + tableCounts());
        cleanDatabase();
    }

    @BeforeEach void prepareAccountsAndCourses() throws Exception {
        cleanDatabase();
        teacher = account("teacher", "teacher"); otherTeacher = account("other-teacher", "teacher");
        student = account("student", "student"); otherStudent = account("other-student", "student");
        course = course("课程一"); otherCourse = course("课程二");
    }

    @AfterEach void removeTestData() throws Exception { cleanDatabase(); }

    @AfterAll void assertDatabaseIsClean() throws Exception {
        cleanDatabase();
        Map<String, Long> counts = tableCounts();
        assertTrue(counts.values().stream().allMatch(count -> count == 0), counts.toString());
        System.out.println("测试后业务表行数：" + counts);
    }

    @Test void teacherAddsExistingUsernameOrEmailWithoutCreatingAccounts() throws Exception {
        addStudent(course, "  STUDENT  ", teacher, 200);
        addStudent(course, student.getEmail(), teacher, 200);
        assertEquals(1, membershipCount(course, student));
        assertEquals(4, count("account_user"));
        assertEquals(0, count("learning_record"));
    }

    @Test void addingMissingNonStudentOrArchivedAccountsDoesNotWriteMemberships() throws Exception {
        addStudent(course, "does-not-exist", teacher, 404);
        addStudent(course, teacher.getUsername(), teacher, 422);
        jdbc.update("UPDATE account_user SET archived=TRUE WHERE id=?", student.getId());
        addStudent(course, student.getUsername(), teacher, 422);
        assertEquals(0, membershipCount(course, student));
        assertEquals(4, count("account_user"));
    }

    @Test void onlyTheCoursesTeacherCanManageItsStudents() throws Exception {
        addStudent(course, student.getUsername(), otherTeacher, 403);
        addStudent(course, otherStudent.getUsername(), student, 403);
        http.perform(post("/api/courses/{id}/students", course.getId()).contentType("application/json")
            .content("{\"account\":\"student\"}")).andExpect(status().isUnauthorized());
        assertEquals(0, membershipCount(course, student));
    }

    @Test void studentJoinIsIdempotentAndRecordsAreCreatedOnlyOnStartingTasks() throws Exception {
        TeachingSession task = task(course, "讲义");
        joinCourse(course.getJoinCode(), student, 200); joinCourse(course.getJoinCode(), student, 200);
        assertEquals(1, membershipCount(course, student)); assertEquals(0, count("learning_record"));
        http.perform(get("/api/courses").cookie(cookie(student))).andExpect(status().isOk())
            .andExpect(jsonPath("$[0].id").value(course.getId()));
        String first = http.perform(post("/api/sessions/{id}/start", task.getId()).cookie(cookie(student)))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        String second = http.perform(post("/api/sessions/{id}/start", task.getId()).cookie(cookie(student)))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        assertEquals(JSONUtil.parseObj(first).getStr("id"), JSONUtil.parseObj(second).getStr("id"));
        assertEquals(1, count("learning_record"));
    }

    @Test void invalidCodesAndUnavailableCoursesCannotBeJoined() throws Exception {
        joinCourse(course.getCode(), student, 404); joinCourse("invalid", student, 404);
        joinCourse(course.getJoinCode(), teacher, 403);
        courses.archive(course.getId(), true, teacher); joinCourse(course.getJoinCode(), student, 404);
        Course workbench = courses.workbench(teacher); joinCourse(workbench.getJoinCode(), student, 404);
        assertEquals(0, membershipCount(course, student));
    }

    @Test void firstPublishRequiresAFutureDeadline() throws Exception {
        TeachingSession draft = draftTask(course, "必须定时");
        for (Map<String, Object> input : List.<Map<String, Object>>of(
            Map.of("revision", draft.getRevision()),
            Map.of("revision", draft.getRevision(), "closesAt", "invalid"),
            Map.of("revision", draft.getRevision(), "closesAt", "2020-01-01T00:00:00Z"))) {
            http.perform(post("/api/sessions/{id}/publish", draft.getId()).cookie(cookie(teacher))
                .contentType("application/json").content(JSONUtil.toJsonStr(input))).andExpect(status().isUnprocessableEntity());
        }
        TeachingSession unchanged = sessions.getById(draft.getId());
        assertNull(unchanged.getPublishedVersionId());
        assertFalse(unchanged.getAvailable());
    }

    @Test void publishingWithADeadlineOpensImmediately() throws Exception {
        enrol(course, student);
        TeachingSession draft = draftTask(course, "立即开放");
        String closesAt = Instant.now().plusSeconds(3600).truncatedTo(java.time.temporal.ChronoUnit.MILLIS).toString();
        http.perform(post("/api/sessions/{id}/publish", draft.getId()).cookie(cookie(teacher))
            .contentType("application/json").content(JSONUtil.toJsonStr(Map.of("revision", draft.getRevision(), "closesAt", closesAt))))
            .andExpect(status().isOk());
        TeachingSession task = sessions.getById(draft.getId());
        assertNotNull(task.getUpdatedAt());
        http.perform(get("/api/sessions/{id}", task.getId()).cookie(cookie(teacher)))
            .andExpect(status().isOk()).andExpect(jsonPath("$.availabilityStatus").value("open"))
            .andExpect(jsonPath("$.closesAt").value(closesAt)).andExpect(jsonPath("$.opensAt").doesNotExist());
        http.perform(get("/api/courses/{id}/sessions", course.getId()).cookie(cookie(student)))
            .andExpect(status().isOk()).andExpect(jsonPath("$[0].availabilityStatus").value("open"));
        http.perform(post("/api/sessions/{id}/start", task.getId()).cookie(cookie(student))).andExpect(status().isOk());
    }

    @Test void expirationClosesStudentAccessAndReopeningPreservesTheLearningRecord() throws Exception {
        enrol(course, student);
        CourseMaterial source = courseMaterial(course, "ready", null);
        TeachingSession task = task(course, "截止后重新启用", source.getId());
        LearningRecord previous = record(task, student);
        CourseMaterial answerFile = attachment(previous, "ready");
        assertTrue(task.openAt(task.getClosesAt().minusNanos(1)));
        assertFalse(task.openAt(task.getClosesAt()));
        jdbc.update("UPDATE teaching_session SET closes_at=UTC_TIMESTAMP(3)-INTERVAL 1 MINUTE WHERE id=?", task.getId());
        assertTrue(sessions.getById(task.getId()).getAvailable(), "到期校验须在后台写入前立即生效");
        assertStudentTaskHidden(task);
        http.perform(get("/api/history").cookie(cookie(student))).andExpect(status().isOk()).andExpect(jsonPath("$").isEmpty());
        http.perform(put("/api/records/{id}/answers", previous.getId()).cookie(cookie(student)).contentType("application/json")
            .content(JSONUtil.toJsonStr(Map.of("revision", previous.getRevision(), "answers", Map.of("q1", "新答案")))))
            .andExpect(status().isNotFound());
        http.perform(post("/api/records/{id}/submit", previous.getId()).cookie(cookie(student)).contentType("application/json")
            .content(JSONUtil.toJsonStr(Map.of("revision", previous.getRevision())))).andExpect(status().isNotFound());
        http.perform(get("/api/records/{id}/export", previous.getId()).cookie(cookie(student))).andExpect(status().isNotFound());
        http.perform(get("/api/records/{id}/attachments", previous.getId()).cookie(cookie(student))).andExpect(status().isNotFound());
        http.perform(get("/api/materials/{id}/file", answerFile.getId()).cookie(cookie(student))).andExpect(status().isNotFound());
        http.perform(get("/api/materials/{id}/text", source.getId()).param("versionId", task.getPublishedVersionId())
            .cookie(cookie(student))).andExpect(status().isNotFound());
        http.perform(get("/api/records/{id}/observe", previous.getId()).cookie(cookie(teacher))).andExpect(status().isOk());
        http.perform(get("/api/sessions/{id}", task.getId()).cookie(cookie(teacher)))
            .andExpect(status().isOk()).andExpect(jsonPath("$.availabilityStatus").value("expired"));
        sessions.expireTasks();
        assertFalse(sessions.getById(task.getId()).getAvailable());
        assertFalse(sessions.getById(task.getId()).getArchived());

        Requests.TaskSchedule updateContent = new Requests.TaskSchedule(); updateContent.setRevision(task.getRevision());
        sessions.publish(task.getId(), updateContent, teacher);
        assertFalse(sessions.getById(task.getId()).getAvailable());
        TeachingSession reopened = sessions.schedule(task.getId(), closingSchedule(sessions.getById(task.getId())), teacher);
        assertEquals(task.getPublishedVersionId(), reopened.getPublishedVersionId());
        assertEquals(1, count("session_version"));
        assertEquals(previous.getId(), learning.start(task.getId(), null, student).getId());
        assertEquals(previous.getAnswersJson(), records.selectById(previous.getId()).getAnswersJson());
        assertEquals(previous.getMessagesJson(), records.selectById(previous.getId()).getMessagesJson());
        assertTrue(historiesFor(previous) > 0);
        http.perform(get("/api/materials/{id}/file", answerFile.getId()).cookie(cookie(student))).andExpect(status().isOk());
        http.perform(put("/api/records/{id}/answers", previous.getId()).cookie(cookie(student)).contentType("application/json")
            .content(JSONUtil.toJsonStr(Map.of("revision", previous.getRevision(), "answers", Map.of("q1", "继续作答")))))
            .andExpect(status().isOk());
    }

    @Test void recycledPublishedTaskRequiresAValidScheduleAndCourseTeacher() throws Exception {
        enrol(course, student);
        TeachingSession task = task(course, "从回收站恢复");
        LearningRecord previous = record(task, student);
        learning.submit(previous.getId(), previous.getRevision(), student);
        sessions.archive(task.getId(), true, teacher);
        TeachingSession recycled = sessions.getById(task.getId());
        assertTrue(recycled.getArchived());
        assertFalse(recycled.getAvailable());
        assertStudentTaskHidden(task);
        http.perform(post("/api/sessions/{id}/archive", task.getId()).param("archived", "false").cookie(cookie(teacher)))
            .andExpect(status().isUnprocessableEntity());
        String payload = JSONUtil.toJsonStr(closingSchedule(recycled));
        for (AccountUser outsider : List.of(student, otherTeacher)) {
            http.perform(put("/api/sessions/{id}/availability", task.getId()).cookie(cookie(outsider))
                .contentType("application/json").content(payload)).andExpect(status().isForbidden());
        }
        http.perform(put("/api/sessions/{id}/availability", task.getId()).cookie(cookie(teacher))
            .contentType("application/json").content(payload)).andExpect(status().isOk())
            .andExpect(jsonPath("$.availabilityStatus").value("open")).andExpect(jsonPath("$.archived").value(false));
        assertEquals(previous.getId(), learning.start(task.getId(), null, student).getId());
        assertEquals("submitted", records.selectById(previous.getId()).getStatus());
    }

    @Test void restoringADraftDoesNotMakeItAvailable() throws Exception {
        enrol(course, student);
        TeachingSession task = draftTask(course, "恢复草稿");
        sessions.archive(task.getId(), true, teacher);
        sessions.archive(task.getId(), false, teacher);
        TeachingSession restored = sessions.getById(task.getId());
        assertFalse(restored.getArchived());
        assertFalse(restored.getAvailable());
        assertNull(restored.getPublishedVersionId());
        assertStudentTaskHidden(restored);
    }

    private void assertStudentTaskHidden(TeachingSession task) throws Exception {
        http.perform(get("/api/courses/{id}/sessions", course.getId()).cookie(cookie(student)))
            .andExpect(status().isOk()).andExpect(jsonPath("$").isEmpty());
        http.perform(get("/api/sessions/{id}/workspace", task.getId()).cookie(cookie(student))).andExpect(status().isNotFound());
        http.perform(post("/api/sessions/{id}/start", task.getId()).cookie(cookie(student))).andExpect(status().isNotFound());
    }

    @Test void assessmentUsesTheSubmittedQuestionsAndExportsOnlyPublicFeedback() throws Exception {
        enrol(course, student);
        TeachingSession task = task(course, "评价提交快照");
        LearningRecord record = record(task, student);
        http.perform(post("/api/records/{id}/submit", record.getId()).cookie(cookie(student)).contentType("application/json")
            .content(JSONUtil.toJsonStr(Map.of("revision", record.getRevision()))))
            .andExpect(status().isOk()).andExpect(jsonPath("$.assessment.status").value("queued"));
        LearningAssessment queued = latestAssessment(record);
        assertEquals(records.selectById(record.getId()).getRevision(), queued.getSubmissionRevision());

        var changed = JSONUtil.toBean(JSONUtil.toJsonStr(sessions.view(task, true)), Requests.SessionInput.class);
        changed.getContent().getQuestions().get(0).setPrompt("更新后的题目。");
        changed.getContent().getQuestions().get(0).setReferenceAnswer("更新后的参考答案");
        sessions.edit(task.getId(), changed, teacher);
        when(ai.assessAnswers(any(), anyList(), anyMap())).thenAnswer(call -> {
            FormativeAssessment.Submission input = call.getArgument(0);
            assertEquals("教师参考答案", input.questions().get(0).referenceAnswer());
            assertEquals("说明你的思路。", input.questions().get(0).prompt());
            assertEquals("学生作答", input.questions().get(0).answer());
            return feedbackFor(call.getArgument(1));
        });
        assessments.processNext();
        var response = http.perform(get(assessmentPath(record, queued)).cookie(cookie(student)))
            .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("completed"))
            .andExpect(jsonPath("$.feedback.questions[0].prompt").value("说明你的思路。"))
            .andExpect(jsonPath("$.inputJson").doesNotExist()).andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        assertFalse(response.contains("教师参考答案"));
        http.perform(get(assessmentPath(record, queued)).cookie(cookie(otherStudent))).andExpect(status().isForbidden());
        var markdown = http.perform(get("/api/records/{id}/export", record.getId()).cookie(cookie(student)))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        assertTrue(markdown.contains("AI 形成性评价"));
        assertTrue(markdown.contains("补充一条可核对的依据"));
        assertFalse(markdown.contains("教师参考答案") || markdown.contains("更新后的参考答案"));
    }

    @Test void assessmentRetryAndTeacherScoreAreIndependent() throws Exception {
        enrol(course, student);
        TeachingSession task = task(course, "评价重试");
        LearningRecord record = record(task, student);
        learning.submit(record.getId(), record.getRevision(), student);
        LearningAssessment assessment = latestAssessment(record);
        when(ai.assessAnswers(any(), anyList(), anyMap()))
            .thenThrow(new IllegalStateException("provider failure"))
            .thenAnswer(call -> feedbackFor(call.getArgument(1)));
        assessments.processNext();
        assertEquals("failed", assessments.getById(assessment.getId()).getStatus());
        assertEquals("submitted", records.selectById(record.getId()).getStatus());
        String score = assessmentPath(record, assessment) + "/score";
        for (AccountUser person : List.of(student, otherTeacher)) {
            http.perform(put(score).cookie(cookie(person)).contentType("application/json").content("{\"score\":82.5}"))
                .andExpect(status().isForbidden());
        }
        http.perform(put(score).cookie(cookie(teacher)).contentType("application/json").content("{\"score\":101}"))
            .andExpect(status().isUnprocessableEntity());
        http.perform(put(score).cookie(cookie(teacher)).contentType("application/json").content("{\"score\":82.5}"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.teacherScore").value(82.5));
        String retry = assessmentPath(record, assessment) + "/retry";
        http.perform(post(retry).cookie(cookie(student))).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("queued"));
        http.perform(post(retry).cookie(cookie(student))).andExpect(status().isConflict());
        assessments.processNext();
        http.perform(get(assessmentPath(record, assessment)).cookie(cookie(student)))
            .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("completed"))
            .andExpect(jsonPath("$.teacherScore").value(82.5));
        http.perform(put(score).cookie(cookie(teacher)).contentType("application/json").content("{\"score\":null}"))
            .andExpect(status().isOk());
        assertNull(assessments.getById(assessment.getId()).getTeacherScore());
    }

    @Test void resubmissionKeepsThePreviousAssessmentAndItsScore() throws Exception {
        enrol(course, student);
        TeachingSession task = task(course, "评价历史");
        LearningRecord record = record(task, student);
        learning.submit(record.getId(), record.getRevision(), student);
        LearningAssessment first = latestAssessment(record);
        when(ai.assessAnswers(any(), anyList(), anyMap())).thenAnswer(call -> feedbackFor(call.getArgument(1)));
        assessments.processNext();
        assessments.saveScore(record.getId(), first.getId(), java.math.BigDecimal.valueOf(93));
        Requests.Review review = new Requests.Review();
        review.setStatus("needsRevision"); review.setRevision(records.selectById(record.getId()).getRevision());
        learning.review(record.getId(), review, teacher);
        Requests.Answer answer = new Requests.Answer();
        answer.setRevision(records.selectById(record.getId()).getRevision()); answer.setAnswers(Map.of("q1", "修订后的作答"));
        learning.saveAnswers(record.getId(), answer, student);
        learning.submit(record.getId(), records.selectById(record.getId()).getRevision(), student);
        LearningAssessment next = latestAssessment(record);
        assertNotEquals(first.getId(), next.getId());
        assertNull(next.getTeacherScore());
        assessments.processNext();
        http.perform(get("/api/records/{id}/assessments", record.getId()).cookie(cookie(student)))
            .andExpect(status().isOk()).andExpect(jsonPath("$.items[0].id").value(next.getId()))
            .andExpect(jsonPath("$.items[1].teacherScore").value(93));
        assertTrue(assessments.getById(first.getId()).getFeedbackJson().contains("学生作答"));
        assertTrue(assessments.getById(next.getId()).getFeedbackJson().contains("修订后的作答"));
    }

    @Test void onlyLinkedQuestionAttachmentsAreAssessmentEvidence() throws Exception {
        enrol(course, student);
        TeachingSession task = task(course, "附件作答");
        LearningRecord record = learning.start(task.getId(), null, student);
        CourseMaterial linked = attachment(record, "queued");
        CourseMaterial chatFile = attachment(record, "ready");
        jdbc.update("UPDATE course_material SET question_id=NULL WHERE id=?", chatFile.getId());
        assertThrows(ResponseStatusException.class, () -> learning.submit(record.getId(), record.getRevision(), student));
        assertEquals(0, count("learning_assessment"));
        jdbc.update("UPDATE course_material SET status='ready' WHERE id=?", linked.getId());
        learning.submit(record.getId(), record.getRevision(), student);
        when(ai.assessAnswers(any(), anyList(), anyMap())).thenAnswer(call -> {
            FormativeAssessment.Submission input = call.getArgument(0);
            assertEquals(List.of(linked.getId()), input.sources().values().stream().map(FormativeAssessment.Source::materialId).toList());
            var question = input.questions().get(0);
            assertEquals(List.of("source1"), question.studentSources());
            return List.of(new FormativeAssessment.QuestionFeedback(1, question.id(), question.prompt(), "partial",
                linked.getTitle(), "测试材料", "你已提交材料。", "补充论证。", "补充一条可核对的依据。"));
        });
        assessments.processNext();
        assertEquals("completed", latestAssessment(record).getStatus());
    }

    @Test void expirationDoesNotDiscardAcceptedAssessmentAndRemovalCascades() throws Exception {
        enrol(course, student);
        TeachingSession task = task(course, "截止后评价");
        LearningRecord record = record(task, student);
        learning.submit(record.getId(), record.getRevision(), student);
        jdbc.update("UPDATE teaching_session SET closes_at=UTC_TIMESTAMP(3)-INTERVAL 1 MINUTE WHERE id=?", task.getId());
        when(ai.assessAnswers(any(), anyList(), anyMap())).thenAnswer(call -> feedbackFor(call.getArgument(1)));
        assessments.processNext();
        LearningAssessment assessment = latestAssessment(record);
        http.perform(get(assessmentPath(record, assessment)).cookie(cookie(student))).andExpect(status().isNotFound());
        http.perform(get(assessmentPath(record, assessment)).cookie(cookie(teacher)))
            .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("completed"));
        kick(course, student, teacher, 204);
        assertNull(assessments.getById(assessment.getId()));
    }

    private List<FormativeAssessment.QuestionFeedback> feedbackFor(List<FormativeAssessment.Question> questions) {
        return questions.stream().map(q -> new FormativeAssessment.QuestionFeedback(q.number(), q.id(), q.prompt(), "partial",
            "", q.answer(), "你给出了自己的判断。", "需要给出支持理由。", "补充一条可核对的依据。")).toList();
    }

    private LearningAssessment latestAssessment(LearningRecord record) {
        return assessments.lambdaQuery().eq(LearningAssessment::getRecordId, record.getId())
            .orderByDesc(LearningAssessment::getSubmissionRevision).last("LIMIT 1").one();
    }

    private String assessmentPath(LearningRecord record, LearningAssessment assessment) {
        return "/api/records/" + record.getId() + "/assessments/" + assessment.getId();
    }

    @Test void simultaneousTeacherAndStudentEnrolmentCreatesOneMembership() throws Exception {
        ExecutorService workers = Executors.newFixedThreadPool(6);
        CountDownLatch ready = new CountDownLatch(6), start = new CountDownLatch(1);
        try {
            List<Future<?>> requests = new ArrayList<>();
            for (int index = 0; index < 6; index++) {
                boolean teacherRequest = index % 2 == 0;
                requests.add(workers.submit(() -> {
                    ready.countDown(); await(start);
                    if (teacherRequest) {
                        Requests.CourseStudent input = new Requests.CourseStudent(); input.setAccount(student.getUsername());
                        courses.addStudent(course.getId(), input, teacher);
                    } else courses.join(course.getJoinCode(), student);
                }));
            }
            assertTrue(ready.await(10, TimeUnit.SECONDS)); start.countDown();
            for (Future<?> request : requests) request.get(20, TimeUnit.SECONDS);
            assertEquals(1, membershipCount(course, student));
        } finally { start.countDown(); workers.shutdownNow(); assertTrue(workers.awaitTermination(10, TimeUnit.SECONDS)); }
    }

    @Test void kickingDeletesOnlyThatStudentsRecordsAcrossTheCourseAndRevokesOldLinks() throws Exception {
        enrol(course, student); enrol(course, otherStudent); enrol(otherCourse, student);
        TeachingSession firstTask = task(course, "任务一"), secondTask = task(course, "任务二");
        LearningRecord first = record(firstTask, student), second = record(secondTask, student);
        LearningRecord classmatesRecord = record(firstTask, otherStudent), otherCourseRecord = record(task(otherCourse, "其他课程任务"), student);
        LearningRecord preview = learning.startPreview(firstTask.getId(), teacher);
        CourseMaterial file = attachment(first, "ready");
        attachment(second, "queued");
        kick(course, student, teacher, 204);
        assertNull(records.selectById(first.getId())); assertNull(records.selectById(second.getId()));
        assertEquals(0, historiesFor(first)); assertEquals(0, historiesFor(second));
        assertNotNull(records.selectById(classmatesRecord.getId())); assertNotNull(records.selectById(otherCourseRecord.getId()));
        assertNotNull(records.selectById(preview.getId())); assertNotNull(accounts.selectById(student.getId()));
        assertEquals(1, membershipCount(otherCourse, student));
        http.perform(get("/api/sessions/{id}/workspace", firstTask.getId()).cookie(cookie(student))).andExpect(status().isForbidden());
        http.perform(get("/api/materials/{id}/file", file.getId()).cookie(cookie(student))).andExpect(status().isForbidden());
        http.perform(put("/api/records/{id}/answers", first.getId()).cookie(cookie(student)).contentType("application/json")
            .content("{\"revision\":0,\"answers\":{}}")).andExpect(status().isNotFound());
        String history = http.perform(get("/api/history").cookie(cookie(student))).andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        assertFalse(history.contains(first.getId())); assertTrue(history.contains(otherCourseRecord.getId()));
        assertAttachmentRecycled(file);
    }

    @Test void onlyTeacherReAddingCanRestoreAccessAndDeletedRecordsDoNotReturn() throws Exception {
        enrol(course, student); TeachingSession task = task(course, "任务"); LearningRecord old = record(task, student);
        kick(course, student, teacher, 204); kick(course, student, teacher, 204);
        joinCourse(course.getJoinCode(), student, 403);
        addStudent(course, student.getUsername(), teacher, 200);
        assertEquals(0, count("learning_record")); assertEquals(0, count("learning_record_history"));
        LearningRecord fresh = learning.start(task.getId(), null, student);
        assertNotEquals(old.getId(), fresh.getId()); assertEquals("{}", fresh.getAnswersJson());
        assertEquals("[]", fresh.getMessagesJson()); assertEquals(1, membershipCount(course, student));
    }

    @Test void kickingAlsoDeletesLegacyVersionRecordsAndTheirHistory() throws Exception {
        enrol(course, student); TeachingSession task = task(course, "兼容旧版本记录");
        LearningRecord current = record(task, student);
        SessionVersion legacy = JSONUtil.toBean(JSONUtil.toJsonStr(versions.selectById(task.getPublishedVersionId())), SessionVersion.class);
        legacy.setId(UUID.randomUUID().toString()); legacy.setRevision(legacy.getRevision() - 1); versions.insert(legacy);
        LearningRecord old = JSONUtil.toBean(JSONUtil.toJsonStr(current), LearningRecord.class);
        old.setId(UUID.randomUUID().toString()); old.setVersionId(legacy.getId()); records.insert(old);
        jdbc.update("INSERT INTO learning_record_history(record_id,kind,payload_json,created_at) VALUES (?,'conversation','{}',UTC_TIMESTAMP(3))", old.getId());
        assertEquals(2, count("learning_record"));
        kick(course, student, teacher, 204);
        assertNull(records.selectById(current.getId())); assertNull(records.selectById(old.getId()));
        assertEquals(0, historiesFor(current)); assertEquals(0, historiesFor(old));
    }

    @Test void kickRejectsOtherTeachersStudentsAndTeacherMemberships() throws Exception {
        enrol(course, student); LearningRecord record = record(task(course, "任务"), student);
        kick(course, student, otherTeacher, 403); kick(course, student, otherStudent, 403);
        kick(course, teacher, teacher, 403); kick(course, otherStudent, teacher, 404);
        http.perform(delete("/api/courses/{id}/students/{studentId}", course.getId(), student.getId())).andExpect(status().isUnauthorized());
        assertNotNull(records.selectById(record.getId())); assertEquals(1, membershipCount(course, student));
    }

    @Test void removedCreationAndArchiveEndpointsCannotBeUsed() throws Exception {
        for (String path : List.of("/api/courses/" + course.getId() + "/student-invitations",
            "/api/courses/" + course.getId() + "/members/batch", "/api/courses/" + course.getId() + "/members/" + student.getId() + "/archive"))
            http.perform(post(path).cookie(cookie(teacher)).contentType("application/json").content("{}"))
                .andExpect(status().isNotFound());
        http.perform(post("/api/courses/{id}/members", course.getId()).cookie(cookie(teacher)))
            .andExpect(status().isMethodNotAllowed());
        assertEquals(4, count("account_user"));
    }

    @Test void kickWaitsForAnInFlightStartAndDeletesItsNewRecord() throws Exception {
        enrol(course, student); TeachingSession task = task(course, "并发开始任务");
        runOverlappingTransactions(() -> learning.start(task.getId(), null, student), () -> {
            courses.removeStudent(course.getId(), student.getId(), teacher); return null;
        });
        assertEquals(0, count("learning_record")); assertEquals(0, membershipCount(course, student));
    }

    @Test void aStartBlockedByKickCannotCreateARecordAfterRemovalCommits() throws Exception {
        enrol(course, student); TeachingSession task = task(course, "并发移出课程");
        runOverlappingTransactions(() -> { courses.removeStudent(course.getId(), student.getId(), teacher); return null; }, () -> {
            ResponseStatusException error = assertThrows(ResponseStatusException.class, () -> learning.start(task.getId(), null, student));
            assertEquals(403, error.getStatusCode().value()); return null;
        });
        assertEquals(0, count("learning_record"));
    }

    @ParameterizedTest @ValueSource(strings = {"student", "task", "course"})
    void processingAttachmentsBlockDeletionAndRollBackAllChanges(String operation) throws Exception {
        enrol(course, student); TeachingSession task = task(course, "处理中附件"); LearningRecord record = record(task, student);
        CourseMaterial file = attachment(record, "processing");
        if (operation.equals("task")) sessions.archive(task.getId(), true, teacher);
        deleteOperation(operation, task, 409);
        assertNotNull(courses.getById(course.getId())); assertNotNull(sessions.getById(task.getId()));
        assertNotNull(records.selectById(record.getId())); assertTrue(historiesFor(record) > 0);
        assertEquals(1, membershipCount(course, student));
        CourseMaterial unchanged = materials.getById(file.getId());
        assertFalse(unchanged.getArchived()); assertNull(unchanged.getFileRemovedAt());
        assertEquals("processing", unchanged.getStatus()); assertTrue(Files.exists(properties.uploadPath(file.getStoragePath())));
        jdbc.update("UPDATE course_material SET status='ready' WHERE id=?", file.getId());
        deleteOperation(operation, task, operation.equals("student") ? 204 : 200);
        assertNull(records.selectById(record.getId())); assertEquals(0, historiesFor(record));
        assertAttachmentRecycled(file);
    }

    @Test void taskDeletionCascadesAllStudentsAndKeepsSharedMaterialsAndOtherTasks() throws Exception {
        enrol(course, student); enrol(course, otherStudent);
        CourseMaterial shared = courseMaterial(course, "ready", null);
        TeachingSession deleted = task(course, "待删除任务", shared.getId()), retained = task(course, "保留任务", shared.getId());
        LearningRecord first = record(deleted, student), second = record(deleted, otherStudent), keep = record(retained, student);
        CourseMaterial file = attachment(first, "ready"); generation(deleted, "succeeded");
        http.perform(delete("/api/sessions/{id}", deleted.getId()).cookie(cookie(teacher))).andExpect(status().isConflict());
        sessions.archive(deleted.getId(), true, teacher);
        http.perform(delete("/api/sessions/{id}", deleted.getId()).cookie(cookie(teacher))).andExpect(status().isOk());
        assertTaskGone(deleted); assertNull(records.selectById(first.getId())); assertNull(records.selectById(second.getId()));
        assertEquals(0, historiesFor(first)); assertEquals(0, historiesFor(second));
        assertNotNull(records.selectById(keep.getId())); assertNotNull(sessions.getById(retained.getId()));
        assertFalse(materials.getById(shared.getId()).getArchived()); assertTrue(Files.exists(properties.uploadPath(shared.getStoragePath())));
        assertEquals(4, count("account_user")); assertEquals(1, membershipCount(course, student));
        assertAttachmentRecycled(file);
    }

    @Test void courseDeletionCascadesItsDataAndPreservesAccountsAndOtherCourses() throws Exception {
        enrol(course, student); enrol(course, otherStudent); enrol(otherCourse, student);
        TeachingSession firstTask = task(course, "课程任务一"), secondTask = task(course, "课程任务二");
        LearningRecord first = record(firstTask, student), second = record(secondTask, otherStudent);
        LearningRecord keep = record(task(otherCourse, "保留课程任务"), student);
        CourseMaterial file = attachment(first, "ready"), source = courseMaterial(course, "ready", null);
        generation(firstTask, "succeeded");
        http.perform(delete("/api/courses/{id}", course.getId()).cookie(cookie(teacher))).andExpect(status().isOk());
        assertNull(courses.getById(course.getId())); assertTaskGone(firstTask); assertTaskGone(secondTask);
        assertEquals(0, jdbc.queryForObject("SELECT COUNT(*) FROM course_member WHERE course_id=?", Long.class, course.getId()));
        assertNull(records.selectById(first.getId())); assertNull(records.selectById(second.getId()));
        assertEquals(0, historiesFor(first)); assertEquals(0, historiesFor(second));
        assertNotNull(records.selectById(keep.getId())); assertNotNull(courses.getById(otherCourse.getId()));
        assertEquals(4, count("account_user")); assertEquals(1, membershipCount(otherCourse, student));
        assertAttachmentRecycled(file); assertAttachmentRecycled(source);
    }

    @Test void onlyCourseOwnerCanDeleteAndRunningGenerationPreventsDeletion() throws Exception {
        CourseMember colleague = new CourseMember(); colleague.setCourseId(course.getId()); colleague.setUserId(otherTeacher.getId());
        colleague.setRole("teacher"); colleague.setArchived(false); members.insert(colleague);
        http.perform(delete("/api/courses/{id}", course.getId()).cookie(cookie(otherTeacher))).andExpect(status().isForbidden());
        TeachingSession task = task(course, "生成中任务"); generation(task, "running");
        http.perform(delete("/api/courses/{id}", course.getId()).cookie(cookie(teacher))).andExpect(status().isConflict());
        assertNotNull(courses.getById(course.getId())); assertNotNull(sessions.getById(task.getId()));
    }

    @Test void mysqlForeignKeysCascadeTaskRecordsAndTheirHistory() throws Exception {
        enrol(course, student); TeachingSession task = task(course, "外键级联"); LearningRecord record = record(task, student);
        generation(task, "succeeded");
        jdbc.update("DELETE FROM teaching_session WHERE id=?", task.getId());
        assertTaskGone(task); assertNull(records.selectById(record.getId())); assertEquals(0, historiesFor(record));
        assertNotNull(courses.getById(course.getId())); assertNotNull(accounts.selectById(student.getId()));
    }

    private AccountUser account(String username, String role) throws Exception {
        AccountUser user = new AccountUser(); user.setId(UUID.randomUUID().toString()); user.setName(username);
        user.setUsername(username); user.setEmail(username + "@example.test"); user.setRole(role);
        user.setArchived(false); user.setDemo(false); user.setMustChangePassword(false); user.setInvitationEnabled(false); accounts.insert(user);
        AuthSession session = new AuthSession(); session.setId(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
            .digest(token(user).getBytes(StandardCharsets.UTF_8)))); session.setUserId(user.getId());
        session.setExpiresAt(LocalDateTime.now(ZoneOffset.UTC).plusHours(1)); authSessions.insert(session); return user;
    }
    private String token(AccountUser user) { return "membership-test-" + user.getId(); }
    private Cookie cookie(AccountUser user) { return new Cookie("aicademiyaSession", token(user)); }
    private Course course(String title) {
        Requests.CourseInput input = new Requests.CourseInput(); input.setTitle(title); input.setCode("COURSE-" + title);
        return courses.create(input, teacher);
    }
    private TeachingSession task(Course selected, String title, String... materialIds) {
        TeachingSession draft = draftTask(selected, title, materialIds);
        sessions.publish(draft.getId(), closingSchedule(draft), teacher);
        return sessions.getById(draft.getId());
    }
    private TeachingSession draftTask(Course selected, String title, String... materialIds) {
        Requests.SessionInput input = new Requests.SessionInput(); input.setTitle(title); input.setMaterialIds(List.of(materialIds));
        input.getContent().setTeachingMode("autonomous");
        TaskContent.Question question = new TaskContent.Question(); question.setId("q1"); question.setType("openResponse");
        question.setPrompt("说明你的思路。"); question.setReferenceAnswer("教师参考答案"); question.setExplanation("教师解释");
        input.getContent().getQuestions().add(question);
        return sessions.create(selected.getId(), input, teacher);
    }
    private Requests.TaskSchedule closingSchedule(TeachingSession task) {
        Requests.TaskSchedule schedule = new Requests.TaskSchedule();
        schedule.setRevision(task.getRevision());
        schedule.setClosesAt(Instant.now().plus(Duration.ofDays(1)).toString());
        return schedule;
    }
    private void enrol(Course selected, AccountUser person) {
        Requests.CourseStudent input = new Requests.CourseStudent(); input.setAccount(person.getUsername()); courses.addStudent(selected.getId(), input, teacher);
    }
    private LearningRecord record(TeachingSession task, AccountUser person) {
        LearningRecord result = learning.start(task.getId(), null, person);
        Requests.Answer answer = new Requests.Answer(); answer.setRevision(result.getRevision()); answer.setAnswers(Map.of("q1", "学生作答"));
        learning.saveAnswers(result.getId(), answer, person);
        String messages = "[{\"role\":\"user\",\"content\":\"学生问题\"},{\"role\":\"assistant\",\"content\":\"辅导回复\"}]";
        jdbc.update("UPDATE learning_record SET messages_json=?,tutor_state_json=?,teacher_note=? WHERE id=?", messages, "{}", "教师评语", result.getId());
        LearningRecordHistory history = new LearningRecordHistory(); history.setRecordId(result.getId()); history.setKind("conversation");
        history.setPayloadJson("{\"messages\":" + messages + "}"); history.setMessageCount(2); history.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC)); histories.insert(history);
        return records.selectById(result.getId());
    }
    private CourseMaterial attachment(LearningRecord record, String status) throws Exception {
        Course selected = courses.getById(sessions.getById(record.getSessionId()).getCourseId());
        CourseMaterial material = courseMaterial(selected, status, record.getId());
        material.setOwnerId(record.getUserId()); material.setQuestionId("q1"); materials.updateById(material); return material;
    }
    private CourseMaterial courseMaterial(Course selected, String status, String recordId) throws Exception {
        String name = UUID.randomUUID() + ".txt"; Files.createDirectories(properties.uploadRoot());
        Path path = properties.uploadPath(name); Files.writeString(path, "测试材料", StandardCharsets.UTF_8);
        CourseMaterial material = new CourseMaterial(); material.setCourseId(selected.getId()); material.setTitle(name); material.setFileName(name);
        material.setRelativePath(name); material.setStoragePath(name); material.setMimeType("text/plain"); material.setFileSize(Files.size(path));
        material.setRecordId(recordId); material.setVisibility("student"); material.setStatus(status); material.setArchived(false);
        DocumentExtraction.Report report = new DocumentExtraction.Report(); report.setUnitsTotal(1); report.setUnitsProcessed(1); report.setNativeTextUnits(1);
        material.setExtractionReportJson(JSONUtil.toJsonStr(report));
        material.setTextContent("测试材料"); material.setErrorMessage(""); material.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC)); materials.save(material); return material;
    }
    private void generation(TeachingSession task, String status) {
        GenerationJob job = new GenerationJob(); job.setSessionId(task.getId()); job.setOwnerId(teacher.getId()); job.setKind("generate");
        job.setStatus(status); job.setStage("测试"); job.setExpectedRevision(task.getRevision()); job.setRequestJson("{}"); job.setErrorMessage("");
        job.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC)); job.setUpdatedAt(job.getCreatedAt()); jobs.insert(job);
    }
    private void addStudent(Course selected, String account, AccountUser operator, int expected) throws Exception {
        http.perform(post("/api/courses/{id}/students", selected.getId()).cookie(cookie(operator)).contentType("application/json")
            .content(JSONUtil.toJsonStr(Map.of("account", account)))).andExpect(status().is(expected));
    }
    private void joinCourse(String code, AccountUser operator, int expected) throws Exception {
        http.perform(post("/api/courses/join").param("code", code).cookie(cookie(operator))).andExpect(status().is(expected));
    }
    private void kick(Course selected, AccountUser person, AccountUser operator, int expected) throws Exception {
        http.perform(delete("/api/courses/{id}/students/{studentId}", selected.getId(), person.getId()).cookie(cookie(operator))).andExpect(status().is(expected));
    }
    private void deleteOperation(String operation, TeachingSession task, int expected) throws Exception {
        if (operation.equals("student")) kick(course, student, teacher, expected);
        else http.perform(delete(operation.equals("task") ? "/api/sessions/{id}" : "/api/courses/{id}",
            operation.equals("task") ? task.getId() : course.getId()).cookie(cookie(teacher))).andExpect(status().is(expected));
    }
    private long count(String table) { return jdbc.queryForObject("SELECT COUNT(*) FROM " + table, Long.class); }
    private long membershipCount(Course selected, AccountUser person) {
        return jdbc.queryForObject("SELECT COUNT(*) FROM course_member WHERE course_id=? AND user_id=? AND archived=FALSE", Long.class, selected.getId(), person.getId());
    }
    private long historiesFor(LearningRecord record) { return jdbc.queryForObject("SELECT COUNT(*) FROM learning_record_history WHERE record_id=?", Long.class, record.getId()); }
    private void assertTaskGone(TeachingSession task) {
        assertNull(sessions.getById(task.getId()));
        for (String table : List.of("session_version", "learning_record", "generation_job"))
            assertEquals(0, jdbc.queryForObject("SELECT COUNT(*) FROM " + table + " WHERE session_id=?", Long.class, task.getId()));
    }
    private void assertAttachmentRecycled(CourseMaterial material) {
        materials.recycleRemovedAttachments();
        assertFalse(Files.exists(properties.uploadPath(material.getStoragePath())));
        assertTrue(Files.exists(properties.recycleRoot().resolve("removed-materials").resolve(material.getStoragePath())));
        assertNull(materials.getById(material.getId()));
    }
    private <T, R> void runOverlappingTransactions(Callable<T> first, Callable<R> second) throws Exception {
        ExecutorService workers = Executors.newFixedThreadPool(2);
        CountDownLatch firstApplied = new CountDownLatch(1), releaseFirst = new CountDownLatch(1), secondEntered = new CountDownLatch(1);
        try {
            Future<T> firstRequest = workers.submit(() -> new TransactionTemplate(transactionManager).execute(status -> {
                try { T result = first.call(); firstApplied.countDown(); await(releaseFirst); return result; }
                catch (Exception exception) { throw new IllegalStateException(exception); }
            }));
            assertTrue(firstApplied.await(10, TimeUnit.SECONDS));
            Future<R> secondRequest = workers.submit(() -> { secondEntered.countDown(); return second.call(); });
            assertTrue(secondEntered.await(10, TimeUnit.SECONDS));
            assertThrows(TimeoutException.class, () -> secondRequest.get(250, TimeUnit.MILLISECONDS));
            releaseFirst.countDown(); firstRequest.get(15, TimeUnit.SECONDS); secondRequest.get(15, TimeUnit.SECONDS);
        } finally { releaseFirst.countDown(); workers.shutdownNow(); assertTrue(workers.awaitTermination(10, TimeUnit.SECONDS)); }
    }
    private static void await(CountDownLatch latch) {
        try { if (!latch.await(10, TimeUnit.SECONDS)) throw new IllegalStateException("等待并发测试同步点超时。"); }
        catch (InterruptedException exception) { Thread.currentThread().interrupt(); throw new IllegalStateException(exception); }
    }
    private Map<String, Long> tableCounts() {
        Map<String, Long> counts = new LinkedHashMap<>(); TABLES.forEach(table -> counts.put(table, count(table))); return counts;
    }
    private void cleanDatabase() throws Exception {
        if (!"true".equals(System.getProperty("zzm.test.allow-clean")))
            throw new IllegalStateException("未授权清库，拒绝清理测试数据。");
        Files.createDirectories(properties.recycleRoot().resolve("test-cleanup"));
        for (String stored : jdbc.queryForList("SELECT storage_path FROM course_material", String.class)) {
            Path path = properties.uploadPath(stored);
            if (Files.exists(path)) Files.move(path, properties.recycleRoot().resolve("test-cleanup").resolve(UUID.randomUUID() + "-" + path.getFileName()));
        }
        for (String table : TABLES) jdbc.update("DELETE FROM " + table);
    }
}
