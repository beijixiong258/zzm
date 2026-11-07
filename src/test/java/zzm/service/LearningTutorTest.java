package zzm.service;

import zzm.config.AppProperties;
import zzm.dto.*;
import zzm.dto.RetrievalContent.SearchResult;
import zzm.entity.*;
import zzm.integration.*;
import zzm.mapper.*;
import zzm.service.impl.LearningServiceImpl;
import cn.hutool.json.*;
import com.baomidou.mybatisplus.extension.conditions.query.LambdaQueryChainWrapper;
import org.junit.jupiter.api.*;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

class LearningTutorTest {
    LearningServiceImpl service;
    SessionService sessions;
    MaterialService materials;
    LearningRecordMapper records;
    AiService ai;
    QmdClient qmd;
    PdfInputReader pdf;
    LearningRecord record;
    AccountUser user;
    SessionVersion version;
    Requests.Chat request;
    CourseMaterial material;
    TeachingSession publishedTask;

    @BeforeEach @SuppressWarnings("unchecked") void setup() {
        sessions = mock(SessionService.class); materials = mock(MaterialService.class); records = mock(LearningRecordMapper.class);
        ai = mock(AiService.class); qmd = mock(QmdClient.class); pdf = mock(PdfInputReader.class);
        AppProperties properties = new AppProperties(); ContextBudget budget = new ContextBudget();
        service = spy(new LearningServiceImpl(sessions, mock(CourseService.class), materials, ai, properties,
            mock(LearningRecordHistoryMapper.class), mock(AccountService.class), mock(TaskExporter.class),
            new TutorContext(properties, budget), budget, qmd, pdf, new TransactionTemplate(mock(PlatformTransactionManager.class))));
        ReflectionTestUtils.setField(service, "baseMapper", records);
        var query = mock(LambdaQueryChainWrapper.class, call -> Set.of("eq", "isNull").contains(call.getMethod().getName()) ? call.getMock() : RETURNS_DEFAULTS.answer(call));
        when(materials.lambdaQuery()).thenReturn(query); when(query.list()).thenReturn(List.of());
        record = new LearningRecord(); record.setId("record"); record.setUserId("student"); record.setSessionId("task"); record.setVersionId("published");
        record.setPreview(false); record.setRevision(0L); record.setStatus("inProgress"); record.setMessagesJson("[]"); record.setAnswersJson("{\"q1\":\"Option one\"}");
        when(records.selectById("record")).thenReturn(record); when(records.updateById(any(LearningRecord.class))).thenReturn(1);
        var taskQuery = mock(LambdaQueryChainWrapper.class, call -> Set.of("eq", "last").contains(call.getMethod().getName()) ? call.getMock() : RETURNS_DEFAULTS.answer(call));
        publishedTask = new TeachingSession(); publishedTask.setAvailable(true); publishedTask.setPublishedVersionId("published");
        when(sessions.lambdaQuery()).thenReturn(taskQuery); when(taskQuery.one()).thenReturn(publishedTask);
        user = new AccountUser(); user.setId("student"); user.setRole("student");
        TaskContent content = new TaskContent(); content.setHandout("PRIVATE_FULL_HANDOUT".repeat(400));
        var question = new TaskContent.Question(); question.setId("q1"); question.setType("singleChoice"); question.setPrompt("First question");
        question.setOptions(List.of("Option one", "Option two")); question.setReferenceAnswer("Option two"); content.getQuestions().add(question);
        material = new CourseMaterial(); material.setId("teacher-source"); material.setCourseId("course"); material.setStatus("ready"); material.setArchived(false);
        material.setMimeType("text/plain"); material.setTitle("Private teacher file"); material.setVisibility("teacher"); material.setStoragePath("source.txt");
        material.setTextContent("Full teacher source; only read when required.");
        JSONObject snapshot = JSONUtil.createObj().set("courseId", "course").set("title", "Task").set("content", content).set("teachingLanguage", "en")
            .set("materials", List.of(Map.of("id", material.getId(), "visibility", "teacher")));
        version = new SessionVersion(); version.setContentJson(snapshot.toString()); when(sessions.version("task", null)).thenReturn(version);
        when(materials.listByIds(anyCollection())).thenReturn(List.of(material));
        request = new Requests.Chat(); request.setMessage("Explain question 1"); request.setRequestId("request"); request.setRevision(0L);
        doReturn(Map.of("saved", true)).when(service).view(any());
    }
    QwenClient.Completion reply() { return new QwenClient.Completion("A reviewed-style hint", new LinkedHashMap<>()); }

    @Test void screenshotQuestionSearchesTeachingSourcesUsingTheTranscribedFormula() {
        var screenshot = new CourseMaterial(); screenshot.setId("shot"); screenshot.setRecordId(record.getId());
        screenshot.setOwnerId(user.getId()); screenshot.setCourseId("course"); screenshot.setStatus("ready");
        screenshot.setMimeType("image/png"); screenshot.setTitle("Student work");
        screenshot.setTextContent("## Image 1\n" + "Working from the previous example.\n".repeat(60) + "QK^T / \\sqrt{d_k}");
        when(materials.lambdaQuery().list()).thenReturn(List.of(screenshot));
        when(materials.listByIds(Set.of(material.getId(), "shot"))).thenReturn(List.of(material, screenshot));
        request.setFocusQuestionId("q1"); request.setMessage("这步怎么算？"); request.setAttachmentIds(List.of("shot"));
        when(ai.studentReply(anyList(), any())).thenReturn(reply());
        service.chat("record", request, user);
        verify(qmd).searchDocuments(argThat(scopes -> scopes.stream().anyMatch(s -> s.id().equals("m-teacher-source"))
                && scopes.stream().noneMatch(s -> s.id().equals("m-shot"))),
            argThat(query -> query.contains("这步怎么算") && query.contains("\\sqrt{d_k}") && !query.contains("previous example")), eq(5));
    }

    @Test void toolsCannotReadOtherStudentsAndDoNotInjectWholeMaterials() {
        when(qmd.searchDocuments(anyList(), anyString(), anyInt())).thenReturn(List.of(new SearchResult("m-another-student", "bad", "s0", 1, "FORBIDDEN", 1)));
        when(ai.studentReply(anyList(), any())).thenAnswer(call -> {
            String context = call.getArgument(0).toString(); assertFalse(context.contains("PRIVATE_FULL_HANDOUT"));
            assertFalse(context.contains(material.getTextContent())); assertTrue(context.contains("Option two"));
            AiService.TutorAccess access = call.getArgument(1);
            assertTrue(access.read("read_material", JSONUtil.createObj().set("sourceId", "another-student").set("partId", "s0")).toString().contains("not available"));
            assertFalse(access.read("search_materials", JSONUtil.createObj().set("query", "source")).toString().contains("FORBIDDEN"));
            assertTrue(access.read("read_material", JSONUtil.createObj().set("sourceId", "teacher-source").set("partId", "s0")).toString().contains("public=false"));
            return reply();
        });
        service.chat("record", request, user);
        assertNotNull(record.getTutorStateJson()); verify(records).updateById(record);
    }
    @Test void aTaskUpdateDuringGenerationCannotSaveAnOldReply() {
        when(ai.studentReply(anyList(), any())).thenAnswer(call -> { version.setContentJson(JSONUtil.parseObj(version.getContentJson()).set("revision", 99).toString()); return reply(); });
        var error = assertThrows(ResponseStatusException.class, () -> service.chat("record", request, user));
        assertEquals(409, error.getStatusCode().value()); verify(records, never()).updateById(any(LearningRecord.class));
    }
    @Test void aTaskThatClosesDuringTheReplyCannotSaveThatReply() {
        when(ai.studentReply(anyList(), any())).thenAnswer(call -> {
            publishedTask.setClosesAt(LocalDateTime.now(ZoneOffset.UTC).minusSeconds(1));
            return reply();
        });
        var error = assertThrows(ResponseStatusException.class, () -> service.chat("record", request, user));
        assertEquals(404, error.getStatusCode().value());
        verify(records, never()).updateById(any(LearningRecord.class));
    }
    @Test void imageReadResolvesThePartToItsPhysicalPageAndRejectsConflictingPage() throws Exception {
        material.setMimeType("application/pdf");
        var prepared = new RetrievalContent(); prepared.setSourceKey(RetrievalContent.sourceKey(material));
        prepared.append("Parameter count derivation", 46, "native", true); prepared.finish();
        material.setRetrievalJson(RetrievalContent.json(prepared));
        var report = new DocumentExtraction.Report(); report.setUnitsTotal(132); when(pdf.report(material)).thenReturn(report);
        var picture = new java.awt.image.BufferedImage(10, 10, java.awt.image.BufferedImage.TYPE_INT_RGB);
        var output = new java.io.ByteArrayOutputStream(); javax.imageio.ImageIO.write(picture, "jpeg", output); picture.flush();
        when(pdf.image(material, 46)).thenReturn(output.toByteArray());
        when(ai.sourceImage(anyString(), anyInt(), any(), anyString())).thenReturn(new org.springframework.ai.chat.messages.UserMessage("Original page image"));
        when(ai.studentReply(anyList(), any())).thenAnswer(call -> {
            var access = (AiService.TutorAccess) call.getArgument(1);
            var text = JSONUtil.parseObj(access.read("read_material", JSONUtil.createObj().set("sourceId", material.getId()).set("partId", "s0")));
            String locator = text.getStr("partId"); assertTrue(locator.startsWith("part-")); assertNotEquals("s0", locator);
            var resolved = JSONUtil.parseObj(access.read("read_page", JSONUtil.createObj().set("materialId", material.getId()).set("partId", locator)));
            assertEquals(46, resolved.getInt("page")); assertEquals(1, access.pendingImages().size());
            var conflict = JSONUtil.parseObj(access.read("read_page", JSONUtil.createObj().set("materialId", material.getId()).set("partId", locator).set("page", 52)));
            assertEquals(46, conflict.getInt("actualPage")); assertTrue(conflict.containsKey("error"));
            return reply();
        });
        service.chat("record", request, user);
        verify(pdf).image(material, 46); verify(pdf, never()).image(material, 52);
        assertTrue(record.getTutorStateJson().contains("\"page\":46"));
    }
    @Test void indexedLessonHitDoesNotHideAnUnindexedOriginalPdf() {
        material.setMimeType("application/pdf"); material.setTextContent("");
        var report = new DocumentExtraction.Report(); report.setPdfInputMode("images"); report.setUnitsTotal(132);
        when(pdf.report(material)).thenReturn(report);
        var lesson = RetrievalContent.createLessonDocument("t-task", RetrievalContent.lessonText(JSONUtil.parseObj(version.getContentJson())));
        when(qmd.searchDocuments(anyList(), anyString(), anyInt())).thenReturn(List.of(new SearchResult("t-task", lesson.revision(), "s0", 0, "Lesson evidence", 1)));
        request.setMessage("第1题，请核对PDF第41页的公式。");
        when(ai.studentReply(anyList(), any())).thenAnswer(call -> {
            String context = call.getArgument(0).toString();
            assertTrue(context.contains("Lesson evidence")); assertTrue(context.contains("teacher-source"));
            assertTrue(context.contains("\"pages\":132")); assertTrue(context.contains("read_page"));
            var access = (AiService.TutorAccess) call.getArgument(1);
            assertTrue(access.read("read_material", JSONUtil.createObj().set("sourceId", material.getId()).set("partId", "s0")).toString().contains("not prepared"));
            return reply();
        });
        service.chat("record", request, user);
    }
    @Test void removingAMaterialDuringGenerationRevokesFurtherReads() {
        AtomicBoolean removed = new AtomicBoolean();
        when(materials.listByIds(anyCollection())).thenAnswer(call -> removed.get() ? List.of() : List.of(material));
        when(ai.studentReply(anyList(), any())).thenAnswer(call -> { removed.set(true); ((AiService.TutorAccess) call.getArgument(1)).read("read_material", JSONUtil.createObj().set("sourceId", material.getId()).set("partId", "s0")); return reply(); });
        assertThrows(ResponseStatusException.class, () -> service.chat("record", request, user)); verify(records, never()).updateById(any(LearningRecord.class));
    }
    @Test void pendingTeacherFeedbackBlocksGenerationAndSummary() {
        record.setMessagesJson("[{\"role\":\"assistant\",\"content\":\"private pending\",\"pendingReview\":true}]");
        assertThrows(ResponseStatusException.class, () -> service.chat("record", request, user)); verifyNoInteractions(ai);
    }
    @Test void askingAboutInitialAttemptsReadsOriginalMessagesOutsideRecentWindow() {
        var history = new ArrayList<Requests.ChatMessage>();
        for (String text : List.of("第1题我最初选Option two", "This was an incorrect attempt", "第1题我第二次仍选Option two", "Try again")) {
            var item = new Requests.ChatMessage(); item.setRole(history.size() % 2 == 0 ? "user" : "assistant"); item.setContent(text); history.add(item);
        }
        for (int i = 0; i < 30; i++) {
            var item = new Requests.ChatMessage(); item.setRole(i % 2 == 0 ? "user" : "assistant"); item.setContent("Later unrelated discussion " + i); history.add(item);
        }
        record.setMessagesJson(JSONUtil.toJsonStr(history));
        request.setMessage("第1题我最初两次选了什么？");
        when(ai.studentReply(anyList(), any())).thenAnswer(call -> {
            String prompt = call.getArgument(0).toString();
            assertTrue(prompt.contains("第1题我最初选Option two")); assertTrue(prompt.contains("第1题我第二次仍选Option two"));
            assertFalse(prompt.contains("Later unrelated discussion 0")); return reply();
        });
        service.chat("record", request, user);
    }
    @Test void lightweightEstimateDoesNotSearchSummariseOrReadMaterials() {
        service.context("record", request, user); verifyNoInteractions(ai, qmd, materials);
    }
    @Test void previousConversationRecallPrefetchesApprovedArchivedMessages() {
        var question = new Requests.ChatMessage(); question.setRole("user"); question.setContent("第1题我最初选Option two");
        var reviewed = new Requests.ChatMessage(); reviewed.setRole("assistant"); reviewed.setContent("Approved hint"); reviewed.setOriginalContent("PRIVATE_DRAFT");
        var pending = new Requests.ChatMessage(); pending.setRole("assistant"); pending.setContent("PRIVATE_PENDING"); pending.setPendingReview(true);
        doReturn(Map.of("items", List.of(Map.of("id", "archive")))).when(service).recordHistory("record", "conversation", 1, 1, 0L, user);
        doReturn(Map.of("items", List.of(question, reviewed, pending), "hasMore", true)).when(service).historyMessages("record", "archive", 1, 50, 0L, user);
        request.setMessage("上一段对话里第1题我最初选了什么？请查历史记录。");
        when(ai.studentReply(anyList(), any())).thenAnswer(call -> {
            String prompt = call.getArgument(0).toString();
            assertTrue(prompt.contains("第1题我最初选Option two")); assertTrue(prompt.contains("Approved hint"));
            assertFalse(prompt.contains("PRIVATE_DRAFT")); assertFalse(prompt.contains("PRIVATE_PENDING")); return reply();
        });
        service.chat("record", request, user);
        verify(service).historyMessages("record", "archive", 1, 50, 0L, user);
    }
    @Test void incrementalSummaryIsSavedWithReplyAndCountedInTurnBudget() {
        var messages = new ArrayList<Requests.ChatMessage>();
        for (int i = 0; i < 40; i++) {
            var item = new Requests.ChatMessage(); item.setRole(i % 2 == 0 ? "user" : "assistant"); item.setContent("Approved historical message " + i); messages.add(item);
        }
        record.setMessagesJson(JSONUtil.toJsonStr(messages));
        when(ai.summariseLearning(anyString(), anyList(), anyInt())).thenReturn(new QwenClient.Completion(
            "{\"confirmed\":[\"Discussed question one\"],\"inferred\":[],\"hintsGiven\":[],\"unresolved\":[],\"sources\":[]}",
            Map.of("promptTokensActual", 100, "completionTokensActual", 20, "turnInputEstimate", 90)));
        when(ai.studentReply(anyList(), any())).thenAnswer(call -> {
            assertEquals(100, ((AiService.TutorAccess) call.getArgument(1)).earlierInputTokens());
            assertTrue(call.getArgument(0).toString().contains("Discussed question one")); return reply();
        });
        service.chat("record", request, user);
        var state = JSONUtil.parseObj(record.getTutorStateJson());
        assertEquals(24, state.getInt("coveredMessages")); assertFalse(state.getStr("coveredFingerprint").isBlank());
    }
    @Test void archivedHistoryToolHonoursPageAndOnlyReturnsApprovedText() {
        var reviewed = new Requests.ChatMessage(); reviewed.setRole("assistant"); reviewed.setContent("Approved page two text"); reviewed.setOriginalContent("PRIVATE_DRAFT");
        var pending = new Requests.ChatMessage(); pending.setRole("assistant"); pending.setContent("PRIVATE_PENDING"); pending.setPendingReview(true);
        doReturn(Map.of("items", List.of(reviewed, pending), "hasMore", true)).when(service).historyMessages("record", "archive", 2, 50, 0L, user);
        when(ai.studentReply(anyList(), any())).thenAnswer(call -> {
            var access = (AiService.TutorAccess) call.getArgument(1);
            String value = access.read("read_history", JSONUtil.createObj().set("historyId", "archive").set("page", 2)).toString();
            assertTrue(value.contains("Approved page two text")); assertFalse(value.contains("PRIVATE")); assertTrue(value.contains("hasMore=true"));
            return reply();
        });
        service.chat("record", request, user);
        verify(service).historyMessages("record", "archive", 2, 50, 0L, user);
    }
}
