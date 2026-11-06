package zzm.service;

import zzm.config.AppProperties;
import zzm.dto.*;
import cn.hutool.json.*;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class TutorContextTest {
    final AppProperties properties = new AppProperties();
    final ContextBudget budget = new ContextBudget();
    final TutorContext context = new TutorContext(properties, budget);
    TaskContent content() {
        TaskContent result = new TaskContent();
        for (int i = 1; i <= 3; i++) {
            var question = new TaskContent.Question(); question.setId("q" + i); question.setType("singleChoice");
            question.setPrompt("Question prompt " + i); question.setOptions(List.of("A " + i, "B " + i)); question.setReferenceAnswer("B " + i);
            result.getQuestions().add(question);
        }
        return result;
    }
    Requests.Chat input(String text, String hint) { var result = new Requests.Chat(); result.setMessage(text); result.setFocusQuestionId(hint); return result; }
    Requests.ChatMessage message(String role, String text) { var result = new Requests.ChatMessage(); result.setRole(role); result.setContent(text); return result; }

    @Test void explicitQuestionOverridesUiAndMemory() {
        TutorState state = new TutorState(); state.setQuestionIds(List.of("q1"));
        assertEquals(List.of("q3"), context.focus(content(), input("请解释第三题", "q2"), state).stream().map(TaskContent.Question::getId).toList());
        assertEquals(List.of("q3"), context.focus(content(), input("为什么", "q2"), state).stream().map(TaskContent.Question::getId).toList());
        assertEquals(List.of("q3"), context.focus(content(), input("为什么呢？", "q2"), state).stream().map(TaskContent.Question::getId).toList());
        assertEquals(List.of("q3"), context.focus(content(), input("Why is that?", "q2"), state).stream().map(TaskContent.Question::getId).toList());
        assertTrue(context.focus(content(), input("解释第九题", "q1"), state).isEmpty());
    }
    @Test void invalidUiQuestionIsRejected() { assertThrows(RuntimeException.class, () -> context.focus(content(), input("why", "another-task"), new TutorState())); }
    @Test void retrievalUsesExplicitQuestionButNeverOverridesANewTopicWithUiFocus() {
        var task = content(); var selected = List.of(task.getQuestions().get(1));
        assertEquals("Question prompt 2", context.retrievalQuery(selected, input("第2题我选A，请核对原始讲义的推导和页码。", "q1")));
        assertEquals("How does position encoding work?", context.retrievalQuery(selected, input("How does position encoding work?", "q2")));
    }
    @Test void multipleScreenshotsRetainTheirEvidenceWithinTheSearchQueryLimit() {
        var request = input("长提问".repeat(900), null);
        String query = context.retrievalQuery(List.of(), request, List.of(
            "第一张截图\n" + "一段很长的说明".repeat(200) + " x = " + "z".repeat(2000), "第二张截图\n箭头从 A 指向 B"));
        assertTrue(query.length() <= 2000);
        assertTrue(query.contains("x = ")); assertTrue(query.contains("箭头从 A 指向 B"));
    }
    @Test void memoryIsInvalidatedByContentAndHistoryChanges() {
        var history = List.of(message("user", "one"), message("assistant", "approved"));
        TutorState state = new TutorState(); state.setContentFingerprint("current"); state.setCoveredMessages(2);
        state.setCoveredFingerprint(context.digest(history)); state.setSummary("old learning memory");
        assertEquals(state.getSummary(), context.state(JSONUtil.toJsonStr(state), "current", history).getSummary());
        assertEquals("", context.state(JSONUtil.toJsonStr(state), "updated", history).getSummary());
        history.get(1).setContent("teacher corrected this");
        assertEquals("", context.state(JSONUtil.toJsonStr(state), "current", history).getSummary());
        assertEquals("", context.state(JSONUtil.toJsonStr(state), "current", List.of()).getSummary());
    }
    @Test void longHistoryDoesNotGrowThePromptOrMutateRecords() {
        properties.getTutor().setRecentMessages(6); properties.getTutor().setRecentTokens(600);
        var history = new ArrayList<Requests.ChatMessage>();
        for (int i = 0; i < 100; i++) { history.add(message("user", "old question " + i)); history.add(message("assistant", "explanation " + i)); }
        var task = content(); task.setHandout("FULL_HANDOUT_SHOULD_NOT_BE_SENT".repeat(1000));
        JSONObject snapshot = JSONUtil.createObj().set("content", task).set("additionalInstructions", "MUST_KEEP_THIS_RULE".repeat(100));
        var prompt = context.messages(snapshot, task, JSONUtil.createObj().set("q1", "A 1").set("q2", "SECRET_UNRELATED_ANSWER"),
            List.of(task.getQuestions().get(0)), new TutorState(), history, input("Why?", "q1"));
        String text = prompt.toString();
        assertFalse(text.contains("FULL_HANDOUT")); assertFalse(text.contains("SECRET_UNRELATED_ANSWER"));
        assertTrue(text.contains("MUST_KEEP_THIS_RULE".repeat(100))); assertTrue(text.contains("B 1"));
        assertTrue(prompt.size() <= 11); assertEquals(200, history.size());
    }
    @Test void pendingFeedbackAndOriginalDraftNeverEnterPrompt() {
        var message = message("assistant", "PRIVATE_PENDING_FEEDBACK"); message.setPendingReview(true); message.setOriginalContent("ORIGINAL_DRAFT");
        var approved = message("assistant", "Approved response"); approved.setOriginalContent("OLD_PRIVATE_DRAFT");
        var task = content();
        var prompt = context.messages(JSONUtil.createObj().set("content", task), task, new JSONObject(), List.of(), new TutorState(), List.of(message, approved), input("help", null));
        assertFalse(prompt.toString().contains("PRIVATE")); assertFalse(prompt.toString().contains("ORIGINAL_DRAFT")); assertTrue(prompt.toString().contains("Approved response"));
    }
}
