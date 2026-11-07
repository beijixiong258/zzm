package zzm.service;

import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;
import zzm.config.AppProperties;
import zzm.dto.FormativeAssessment;
import zzm.dto.RetrievalContent;
import zzm.entity.CourseMaterial;
import zzm.integration.QwenClient;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.util.List;
import java.util.Map;
import javax.imageio.ImageIO;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class FormativeAssessmentTest {
    private final QwenClient client = mock(QwenClient.class);
    private final ContextBudget budget = new ContextBudget();
    private final AppProperties properties = new AppProperties();
    private final AiService service = new AiService(client, budget, new PdfInputReader(properties, budget), properties);

    @Test void incompleteBatchRetriesAndKeepsEveryQuestionInOrder() {
        var first = question(1, "核对原文", "查看权威出处");
        var second = question(2, "检查日期", "对照发布日期");
        when(client.complete(anyList(), anyInt(), eq(true), eq(0)))
            .thenReturn(completion(item(1, "answer", "核对原文", "met")))
            .thenReturn(completion(item(2, "answer", "检查日期", "met"), item(1, "answer", "核对原文", "met")));
        var result = assess(first, second);
        assertEquals(List.of(1, 2), result.stream().map(FormativeAssessment.QuestionFeedback::number).toList());
        verify(client, times(2)).complete(anyList(), anyInt(), eq(true), eq(0));
    }

    @Test void quoteFromAnotherQuestionCannotSupportAJudgement() {
        when(client.complete(anyList(), anyInt(), eq(true), eq(0)))
            .thenReturn(completion(item(1, "answer", "检查日期", "met"), item(2, "answer", "检查日期", "met")));
        var failure = assertThrows(ResponseStatusException.class,
            () -> assess(question(1, "核对原文", ""), question(2, "检查日期", "")));
        assertEquals(502, failure.getStatusCode().value());
        verify(client, times(2)).complete(anyList(), anyInt(), eq(true), eq(0));
    }

    @Test void noEvidenceCanBeReportedWithoutInventingAStrength() {
        when(client.complete(anyList(), anyInt(), eq(true), eq(0)))
            .thenReturn(completion(new FormativeAssessment.ModelQuestion(1, "insufficient", "", "", "",
                "目前没有可核对的证据。", "补充你核对的原始出处。")));
        var result = assess(question(1, "", ""));
        assertEquals("insufficient", result.get(0).judgement());
        assertEquals("", result.get(0).strength());
    }

    @Test void privateModelAnswerCannotBeCopiedIntoPublicFeedback() {
        String privateKey = "INSTRUCTOR ONLY: the complete worked solution uses this exact private sentence.";
        when(client.complete(anyList(), anyInt(), eq(true), eq(0)))
            .thenReturn(completion(new FormativeAssessment.ModelQuestion(1, "partial", "answer", "My explanation",
                "You gave a reason.", privateKey, "Check the source.")));
        assertThrows(ResponseStatusException.class, () -> assess(question(1, "My explanation", privateKey)));
    }

    @Test void feedbackCanExplainAMissedChoiceWithoutGivingItAway() {
        var q = new FormativeAssessment.Question(1, "q1", "multipleChoice", "核对哪些政策要素？",
            List.of("生效日期", "适用对象", "点赞数"), null, "[\"生效日期\",\"适用对象\"]", "", "生效日期", List.of(), List.of());
        when(client.complete(anyList(), anyInt(), eq(true), eq(0)))
            .thenReturn(completion(new FormativeAssessment.ModelQuestion(1, "partial", "answer", "生效日期",
                "你找到了生效日期。", "还有一项必需要素。", "补选适用对象。")));
        var result = assess(q).get(0);
        assertEquals("partial", result.judgement());
        assertEquals("你找到了生效日期。", result.strength());
        assertEquals("还有一项必需要素。", result.improvement());
        assertFalse(result.nextStep().contains("适用对象"));
        assertFalse(result.nextStep().isBlank());
    }

    @Test void attachedEvidenceUsesTheActualStudentText() {
        var q = new FormativeAssessment.Question(1, "q1", "openResponse", "说明出处。", List.of(), null,
            "", "", "", List.of("source1"), List.of());
        var input = new FormativeAssessment.Submission("zh-CN", List.of(), "", List.of(q),
            Map.of("source1", new FormativeAssessment.Source("file", "作答.txt", "我查了官方文件。", null, 0, false)));
        when(client.complete(anyList(), anyInt(), eq(true), eq(0)))
            .thenReturn(completion(item(1, "source1", "官方文件", "met")));
        var feedback = service.assessAnswers(input, input.questions(), Map.of()).get(0);
        assertEquals("作答.txt", feedback.evidenceLabel());
        assertEquals("官方文件", feedback.quote());
    }

    @Test void visualEvidenceUsesTheShownAttachmentWithoutAnUnverifiedQuote() throws Exception {
        CourseMaterial file = new CourseMaterial();
        file.setId("student-file");
        file.setMimeType("application/pdf");
        var image = new ByteArrayOutputStream();
        ImageIO.write(new BufferedImage(28, 28, BufferedImage.TYPE_INT_RGB), "jpeg", image);
        PdfInputReader renderer = mock(PdfInputReader.class);
        when(renderer.image(file, 1)).thenReturn(image.toByteArray());
        AiService evaluator = new AiService(client, budget, renderer, properties);
        var question = new FormativeAssessment.Question(1, "q1", "openResponse", "核对附件里的计算过程。", List.of(),
            null, "", "", "", List.of("source1"), List.of());
        var source = new FormativeAssessment.Source(file.getId(), "计算.pdf", "", RetrievalContent.materialKey(file), 1, false);
        var input = new FormativeAssessment.Submission("zh-CN", List.of(), "", List.of(question), Map.of("source1", source));
        when(client.complete(anyList(), anyInt(), eq(true), anyInt()))
            .thenReturn(completion(item(1, "source1", "未经验证的图像转录", "met")));
        assertThrows(ResponseStatusException.class, () -> evaluator.assessAnswers(input, input.questions(), Map.of()));
        var result = evaluator.assessAnswers(input, input.questions(), Map.of(file.getId(), file)).get(0);
        assertEquals("计算.pdf", result.evidenceLabel());
        assertEquals("", result.quote());
    }

    private List<FormativeAssessment.QuestionFeedback> assess(FormativeAssessment.Question... questions) {
        var input = new FormativeAssessment.Submission("zh-CN", List.of(), "", List.of(questions), Map.of());
        return service.assessAnswers(input, input.questions(), Map.of());
    }

    private FormativeAssessment.Question question(int number, String answer, String reference) {
        return new FormativeAssessment.Question(number, "q" + number, "openResponse", "说明你的判断。", List.of(),
            null, reference, "", answer, List.of(), List.of());
    }

    private FormativeAssessment.ModelQuestion item(int number, String evidenceId, String quote, String judgement) {
        return new FormativeAssessment.ModelQuestion(number, judgement, evidenceId, quote, "你提供了具体的核对方法。",
            "", "用同样的方法检查另一条信息。");
    }

    private QwenClient.Completion completion(FormativeAssessment.ModelQuestion... questions) {
        return new QwenClient.Completion(RetrievalContent.json(new FormativeAssessment.ModelResult(List.of(questions))), Map.of());
    }
}
