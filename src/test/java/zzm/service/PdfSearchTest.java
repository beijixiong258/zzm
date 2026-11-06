package zzm.service;

import org.apache.pdfbox.pdmodel.*;
import org.apache.pdfbox.pdmodel.font.*;
import org.apache.pdfbox.pdmodel.common.PDRectangle;
import org.apache.pdfbox.pdmodel.graphics.form.PDFormXObject;
import org.apache.pdfbox.pdmodel.graphics.image.LosslessFactory;
import org.apache.pdfbox.pdmodel.interactive.annotation.PDAnnotationLink;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.*;
import zzm.config.AppProperties;
import zzm.entity.CourseMaterial;
import zzm.integration.QwenClient;
import java.nio.file.Path;
import java.awt.image.BufferedImage;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class PdfSearchTest {
    @TempDir(cleanup = CleanupMode.NEVER) Path directory;

    @Test void pageBackgroundFrameSeparatorAndLinkUseNativeTextWhileAnImageOnlyPageNeedsVision() throws Exception {
        Path source = directory.resolve("source.pdf");
        try (PDDocument document = new PDDocument()) {
            PDPage textPage = new PDPage(), drawingPage = new PDPage();
            document.addPage(textPage); document.addPage(drawingPage);
            var link = new PDAnnotationLink(); link.setRectangle(new PDRectangle(50, 700, 100, 10)); textPage.getAnnotations().add(link);
            try (PDPageContentStream stream = new PDPageContentStream(document, textPage)) {
                stream.setNonStrokingColor(java.awt.Color.WHITE);
                stream.addRect(0, 0, textPage.getCropBox().getWidth(), textPage.getCropBox().getHeight()); stream.fill();
                stream.setNonStrokingColor(java.awt.Color.BLACK);
                stream.beginText(); stream.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 12);
                stream.newLineAtOffset(50, 700); stream.showText("Scaled dot product attention uses a square root scaling factor."); stream.endText();
                stream.addRect(40, 680, 500, 50); stream.stroke();
                stream.moveTo(40, 670); stream.lineTo(540, 670); stream.stroke();
            }
            try (PDPageContentStream stream = new PDPageContentStream(document, drawingPage)) {
                stream.addRect(100, 100, 200, 200); stream.fill();
            }
            document.save(source.toFile());
        }
        AppProperties properties = new AppProperties(); properties.setUploadDir(directory.toString());
        var reader = new PdfInputReader(properties, new ContextBudget());
        var material = new CourseMaterial(); material.setStoragePath("source.pdf");
        var nativePage = reader.searchPage(material, 1);
        assertTrue(nativePage.text().contains("square root")); assertNull(nativePage.image());
        assertNotNull(reader.searchPage(material, 2).image());
        assertNotNull(reader.image(material, 1));
    }

    @Test void formulasInRasterFormsAndVectorOutlinesAreReadAlongsideNativeText() throws Exception {
        Path source = directory.resolve("mixed.pdf");
        try (PDDocument document = new PDDocument()) {
            PDPage raster = new PDPage(), vector = new PDPage(), table = new PDPage();
            document.addPage(raster); document.addPage(vector); document.addPage(table);
            BufferedImage picture = new BufferedImage(180, 48, BufferedImage.TYPE_INT_RGB);
            var brush = picture.createGraphics();
            brush.setColor(java.awt.Color.WHITE); brush.fillRect(0, 0, 180, 48);
            brush.setColor(java.awt.Color.BLACK); brush.drawString("QK^T / sqrt(d_k)", 5, 25);
            brush.dispose();
            var image = LosslessFactory.createFromImage(document, picture); picture.flush();
            var form = new PDFormXObject(document); form.setBBox(new PDRectangle(180, 48)); form.setResources(new PDResources());
            try (var content = new PDFormContentStream(form)) { content.drawImage(image, 0, 0, 180, 48); }
            for (PDPage page : java.util.List.of(raster, vector, table)) {
                try (var stream = new PDPageContentStream(document, page)) {
                    stream.beginText(); stream.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 12);
                    stream.newLineAtOffset(50, 700); stream.showText("See expression below."); stream.endText();
                    if (page == raster) stream.drawForm(form);
                    else if (page == vector) {
                        stream.moveTo(50, 640); stream.lineTo(54, 636); stream.lineTo(60, 650); stream.lineTo(80, 650); stream.stroke();
                    } else {
                        for (int offset = 0; offset <= 100; offset += 50) {
                            stream.moveTo(50, 500 + offset); stream.lineTo(150, 500 + offset); stream.stroke();
                            stream.moveTo(50 + offset, 500); stream.lineTo(50 + offset, 600); stream.stroke();
                        }
                    }
                }
            }
            document.save(source.toFile());
        }
        var properties = new AppProperties(); properties.setUploadDir(directory.toString());
        var reader = new PdfInputReader(properties, new ContextBudget());
        var file = new CourseMaterial(); file.setStoragePath("mixed.pdf");
        for (int page = 1; page <= 3; page++) {
            var result = reader.searchPage(file, page);
            assertEquals("See expression below.", result.text());
            assertNotNull(result.image(), "Missing visual evidence on page " + page);
        }
    }

    @Test void pdfTranscriptionDistinguishesAnEmptyVisualResultFromAMissingResult() throws Exception {
        var client = mock(QwenClient.class);
        var ai = new AiService(client, new ContextBudget(), mock(PdfInputReader.class), new AppProperties());
        var image = new BufferedImage(8, 8, BufferedImage.TYPE_INT_RGB);
        var buffer = new java.io.ByteArrayOutputStream(); javax.imageio.ImageIO.write(image, "jpeg", buffer); image.flush();
        var page = new PdfInputReader.SearchPage("Original text", buffer.toByteArray());
        when(client.complete(anyList(), anyInt(), eq(true), anyInt())).thenReturn(
            new QwenClient.Completion("{\"text\":\"\",\"visualPassages\":[],\"readable\":true,\"issues\":[]}", java.util.Map.of()),
            new QwenClient.Completion("{\"text\":\"Original text\",\"readable\":true,\"issues\":[]}", java.util.Map.of()));
        assertTrue(ai.readPdfForSearch("page 1", page).getVisualPassages().isEmpty());
        assertThrows(org.springframework.web.server.ResponseStatusException.class, () -> ai.readPdfForSearch("page 1", page));
    }
}
