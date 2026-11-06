package zzm.service;

import org.junit.jupiter.api.Test;
import zzm.dto.RetrievalContent;
import zzm.dto.DocumentExtraction;
import zzm.entity.CourseMaterial;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class RetrievalContentTest {
    @Test void chunksRoundTripWithoutLosingSourceTextOrUnicode() {
        String source = "中文段落🙂\n".repeat(1000);
        var material = new CourseMaterial(); material.setId("m1"); material.setStoragePath("m1.pdf"); material.setTextContent(source);
        var content = RetrievalContent.read(material); content.append(source, 7, "native", true); content.finish();
        material.setRetrievalJson(RetrievalContent.json(content));
        var restored = RetrievalContent.read(material);
        assertTrue(restored.isComplete()); assertEquals(content.getRevision(), restored.getRevision());
        assertEquals(source, restored.getParts().stream().map(RetrievalContent.Part::text).collect(java.util.stream.Collectors.joining()));
        assertTrue(restored.getParts().stream().allMatch(p -> p.page() == 7 && p.text().length() <= 2400));
        material.setTextContent("changed"); assertFalse(RetrievalContent.read(material).isComplete());
    }
    @Test void lessonEditsChangeTheRevisionWithoutChangingTheBusinessId() {
        var first = RetrievalContent.lesson("t-task", "First teacher text");
        var second = RetrievalContent.lesson("t-task", "Corrected teacher text");
        assertEquals(first.id(), second.id()); assertNotEquals(first.revision(), second.revision());
    }

    @Test void olderPdfIndicesRestartAtPageOneWhileOtherMaterialsAndTheLearningFingerprintRemainValid() {
        for (String file : List.of("slides.PDF", "slides.docx")) {
            var material = new CourseMaterial(); material.setFileName(file); material.setStoragePath(file); material.setId("m1");
            var oldKey = RetrievalContent.hash("retrieval-1\nm1\n" + file + "\n\n");
            var old = new RetrievalContent(); old.setSourceKey(oldKey); old.setNextPage(12);
            old.append("Old body", 11, "native", true); old.finish();
            material.setRetrievalJson(RetrievalContent.json(old));
            var restored = RetrievalContent.read(material);
            assertEquals(oldKey, RetrievalContent.materialKey(material));
            if (file.endsWith(".PDF")) {
                assertFalse(restored.isComplete()); assertTrue(restored.getParts().isEmpty()); assertEquals(1, restored.getNextPage());
            } else { assertTrue(restored.isComplete()); assertEquals(old.getRevision(), restored.getRevision()); }
        }
    }

    @Test void mixedAndScannedPagesKeepNativeEvidenceSeparateFromVisualEvidence() {
        var index = new RetrievalContent();
        var reading = new DocumentExtraction.VisualReading(); reading.setText("Printed words on the scan");
        String formula = "Eq. 3: QK^T/\\sqrt{d_k}, dot product divided by the square root of the key dimension.";
        reading.setVisualPassages(List.of(formula)); reading.setInputTokens(1500); reading.setReadable(false);
        index.appendPdfPage(4, "Original caption", reading);
        index.appendPdfPage(5, "", reading);
        var parts = index.getParts();
        assertEquals(List.of("Original caption", formula, "Printed words on the scan", formula),
            parts.stream().map(RetrievalContent.Part::text).toList());
        assertEquals(List.of(4, 4, 5, 5), parts.stream().map(RetrievalContent.Part::page).toList());
        assertTrue(parts.get(0).reliable()); assertFalse(parts.get(1).reliable());
        assertEquals(3000L, index.getVisionInputTokens());
    }
}
