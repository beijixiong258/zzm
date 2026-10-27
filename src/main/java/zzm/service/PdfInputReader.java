package zzm.service;

import zzm.config.AppProperties;
import zzm.dto.DocumentExtraction;
import zzm.dto.DocumentExtraction.PageInput;
import zzm.dto.DocumentExtraction.Report;
import zzm.entity.CourseMaterial;
import cn.hutool.json.JSONUtil;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.contentstream.PDContentStream;
import org.apache.pdfbox.contentstream.operator.Operator;
import org.apache.pdfbox.pdfparser.PDFStreamParser;
import org.apache.pdfbox.pdmodel.*;
import org.apache.pdfbox.pdmodel.graphics.form.PDFormXObject;
import org.apache.pdfbox.pdmodel.graphics.image.PDImageXObject;
import org.apache.pdfbox.rendering.PDFRenderer;
import org.apache.pdfbox.text.PDFTextStripper;
import org.springframework.stereotype.Component;
import javax.imageio.*;
import javax.imageio.stream.MemoryCacheImageOutputStream;
import java.awt.Color;
import java.awt.Rectangle;
import java.awt.image.BufferedImage;
import java.io.*;
import java.nio.file.Path;
import java.util.*;
import java.util.function.BiConsumer;
import java.util.function.Consumer;
import static zzm.exception.ApiErrors.error;

/** Local PDF preparation only. No model dependency and no transcription. */
@Slf4j
@Component
@RequiredArgsConstructor
public class PdfInputReader {
    private final AppProperties properties;
    private final ContextBudget budget;

    public static boolean isPdf(CourseMaterial material) {
        return "application/pdf".equalsIgnoreCase(material.getMimeType())
            || Objects.toString(material.getFileName(), "").toLowerCase(Locale.ROOT).endsWith(".pdf");
    }
    public Report report(CourseMaterial material) {
        return material.getExtractionReportJson() == null ? new Report()
            : JSONUtil.toBean(material.getExtractionReportJson(), Report.class);
    }
    public boolean complete(Report report) {
        if (!Set.of("text", "images").contains(Objects.toString(report.getPdfInputMode(), ""))
            || report.isTruncated() || report.getFailedUnits() == null || !report.getFailedUnits().isEmpty()
            || report.getUnitsTotal() <= 0 || report.getUnitsProcessed() != report.getUnitsTotal()
            || report.getPageInputs() == null || report.getPageInputs().size() != report.getUnitsTotal()) return false;
        boolean images = "images".equals(report.getPdfInputMode());
        for (int i = 0; i < report.getPageInputs().size(); i++) {
            PageInput page = report.getPageInputs().get(i);
            if (page.getPage() != i + 1 || !(images ? "image" : "text").equals(page.getKind())
                || !(images ? "prepared" : "extracted").equals(page.getStatus())) return false;
            if (images && (!Float.isFinite(page.getRenderDpi()) || page.getRenderDpi() <= 0 || page.getRenderDpi() > 144
                || page.getWidth() <= 0 || page.getHeight() <= 0 || page.getImageBytes() <= 0
                || page.getOriginalWidth() > 3000 || page.getOriginalHeight() > 3000
                || page.getCropLeft() < 0 || page.getCropTop() < 0
                || (long) page.getCropLeft() + page.getWidth() > page.getOriginalWidth()
                || (long) page.getCropTop() + page.getHeight() > page.getOriginalHeight())) return false;
        }
        return true;
    }
    public DocumentExtraction prepare(Path source, Consumer<Report> progress) {
        DocumentExtraction result = new DocumentExtraction();
        Report report = result.getReport();
        report.setPdfInputMode("inspecting");
        try (PDDocument document = Loader.loadPDF(source.toFile())) {
            boolean extractText = document.getCurrentAccessPermission().canExtractContent();
            report.setUnitsTotal(document.getNumberOfPages());
            progress.accept(report);
            if (report.getUnitsTotal() == 0) throw new IOException("PDF has no pages");
            if (report.getUnitsTotal() > Math.max(1, properties.getDocumentMaxUnits())) {
                report.setTruncated(true);
                result.setStatus("incomplete");
                result.setWarning("The PDF exceeds the page processing limit. Split it into smaller files and upload them again.");
                return result;
            }
            PDFRenderer renderer = new PDFRenderer(document);
            renderer.setSubsamplingAllowed(true);
            PDFTextStripper stripper = extractText ? new PDFTextStripper() : null;
            if (stripper != null) stripper.setSortByPosition(true);
            List<String> pages = new ArrayList<>();
            boolean images = !extractText, oversizedText = false;
            if (!extractText) report.getNotes().add("PDF text extraction is restricted; all pages will be prepared as images.");
            long characters = 0;
            for (int i = 0; i < document.getNumberOfPages(); i++) {
                checkInterrupted();
                report.setCurrentUnit("Page " + (i + 1));
                String text = "";
                if (stripper != null) try {
                    stripper.setStartPage(i + 1); stripper.setEndPage(i + 1);
                    text = stripper.getText(document).strip();
                    // Graphics and annotations are not fully represented by a plain-text extraction.
                    if (!usableText(text) || hasGraphics(document.getPage(i), document.getPage(i).getResources(), 0)
                        || !document.getPage(i).getAnnotations().isEmpty()) images = true;
                    if (!images && text.isBlank()) {
                        BufferedImage page = renderer.renderImageWithDPI(i, dpi(document.getPage(i)));
                        try { if (inkBounds(page) != null) images = true; }
                        finally { page.flush(); }
                    }
                } catch (IOException exception) { images = true; }
                characters += text.length() + 32;
                if (characters > Math.max(1000, properties.getDocumentMaxCharacters())) oversizedText = true;
                pages.add(oversizedText ? "" : text);
                report.setUnitsInspected(i + 1);
                progress.accept(report);
            }
            // Empty documents also retain their complete page sequence as images.
            if (pages.stream().allMatch(String::isBlank) && !oversizedText) images = true;
            report.setPdfInputMode(images ? "images" : "text");
            if (!images && oversizedText) {
                report.setTruncated(true); result.setStatus("incomplete");
                result.setWarning("The PDF exceeds the text processing limit. Split it into smaller files and upload them again.");
                return result;
            }
            StringBuilder text = new StringBuilder();
            for (int i = 0; i < document.getNumberOfPages(); i++) {
                checkInterrupted();
                PageInput input = new PageInput(); input.setPage(i + 1); input.setKind(images ? "image" : "text");
                input.setStatus("preparing"); report.getPageInputs().add(input);
                report.setCurrentUnit("Page " + (i + 1)); progress.accept(report);
                try {
                    if (images) {
                        input.setRenderDpi(dpi(document.getPage(i)));
                        BufferedImage picture = renderer.renderImageWithDPI(i, input.getRenderDpi());
                        try {
                            Rectangle bounds = cropBounds(picture);
                            input.setOriginalWidth(picture.getWidth()); input.setOriginalHeight(picture.getHeight());
                            input.setCropLeft(bounds.x); input.setCropTop(bounds.y);
                            input.setWidth(bounds.width); input.setHeight(bounds.height);
                            input.setCropped(bounds.width != picture.getWidth() || bounds.height != picture.getHeight());
                            input.setImageBytes(jpeg(picture, bounds).length);
                        } finally { picture.flush(); }
                        input.setImageTokensEstimated(budget.imageTokens(input.getWidth(), input.getHeight()));
                        report.setImageInputTokensEstimated(report.getImageInputTokensEstimated() + input.getImageTokensEstimated());
                        input.setStatus("prepared");
                    } else {
                        String pageText = pages.get(i);
                        text.append("\n\n## Page ").append(i + 1).append('\n').append(pageText);
                        input.setTextCharacters(pageText.length()); input.setStatus("extracted");
                        report.setNativeTextUnits(report.getNativeTextUnits() + 1);
                    }
                    report.setUnitsProcessed(report.getUnitsProcessed() + 1);
                } catch (IOException | RuntimeException exception) {
                    input.setStatus("failed"); report.getFailedUnits().add("Page " + (i + 1));
                    log.warn("PDF page {} preparation failed ({})", i + 1, exception.getClass().getSimpleName());
                }
                progress.accept(report);
            }
            result.setText(images ? "" : text.toString().strip());
            report.setTextCharacters(result.getText().length());
            report.setTextTokensEstimated(budget.estimate(result.getText()));
            report.setTextTokensUpperBound(budget.upperBound(result.getText()));
            report.getNotes().add(images
                ? "All PDF pages are prepared as ordered images. No OCR or model request was used during preparation."
                : "The complete PDF text layer was extracted locally. No OCR or model request was used.");
            result.setStatus(complete(report) ? "ready" : "incomplete");
            if (!complete(report)) result.setWarning("PDF preparation is incomplete. Reprocess the file before using it.");
            else if (report.getImageInputTokensEstimated() > ContextBudget.INPUT_LIMIT)
                result.setWarning("Local token estimate is high. This is advisory only; the provider determines capacity and actual usage.");
        } catch (IOException | RuntimeException exception) {
            log.warn("PDF preparation failed ({})", exception.getClass().getSimpleName());
            report.getFailedUnits().add("Document");
            result.setStatus(report.getUnitsProcessed() > 0 ? "incomplete" : "failed");
            result.setWarning("PDF preparation failed. Check for encryption or damage, then retry.");
        } finally {
            report.setCurrentUnit(""); progress.accept(report);
        }
        return result;
    }
    /** Reproduce the prepared geometry only after the complete request has passed its budget gate. */
    public void images(CourseMaterial material, BiConsumer<PageInput, byte[]> consume) {
        Report report = report(material);
        if (!complete(report) || !"images".equals(report.getPdfInputMode()))
            throw error(422, "Reprocess the PDF with the current document parser before continuing.");
        try (PDDocument document = Loader.loadPDF(Path.of(material.getStoragePath()).toFile())) {
            if (document.getNumberOfPages() != report.getUnitsTotal())
                throw new IOException("PDF changed after preparation");
            PDFRenderer renderer = new PDFRenderer(document); renderer.setSubsamplingAllowed(true);
            for (PageInput page : report.getPageInputs()) {
                checkInterrupted();
                BufferedImage picture = renderer.renderImageWithDPI(page.getPage() - 1, page.getRenderDpi());
                try {
                    if (picture.getWidth() != page.getOriginalWidth() || picture.getHeight() != page.getOriginalHeight())
                        throw new IOException("PDF geometry changed after preparation");
                    consume.accept(page, jpeg(picture, new Rectangle(page.getCropLeft(), page.getCropTop(), page.getWidth(), page.getHeight())));
                } finally { picture.flush(); }
            }
        } catch (IOException exception) {
            throw error(422, "The prepared PDF images are unavailable. Reprocess the material before continuing.");
        }
    }
    private void checkInterrupted() throws IOException {
        if (Thread.currentThread().isInterrupted()) throw new IOException("PDF preparation was interrupted");
    }
    private boolean usableText(String text) {
        return text.codePoints().noneMatch(c -> c == 0xFFFD || c == 0 || (Character.isISOControl(c) && !Character.isWhitespace(c)));
    }
    private float dpi(PDPage page) throws IOException {
        double width = page.getCropBox().getWidth(), height = page.getCropBox().getHeight();
        if (!Double.isFinite(width) || !Double.isFinite(height) || width <= 0 || height <= 0) throw new IOException("Invalid PDF page size");
        int edge = Math.max(1000, Math.min(3000, properties.getDocumentImageMaxEdge()));
        return (float) Math.min(144, edge * 72.0 / Math.max(width, height));
    }
    private boolean hasGraphics(PDContentStream stream, PDResources resources, int depth) throws IOException {
        if (depth > 12) return true;
        Object previous = null;
        for (Object token : new PDFStreamParser(stream).parse()) {
            if (token instanceof Operator operator) {
                if (Set.of("BI", "sh", "S", "s", "f", "F", "f*", "B", "B*", "b", "b*").contains(operator.getName())) return true;
                if ("Do".equals(operator.getName()) && previous instanceof org.apache.pdfbox.cos.COSName resource) {
                    if (resources == null) return true;
                    var object = resources.getXObject(resource);
                    if (object instanceof PDImageXObject) return true;
                    if (object instanceof PDFormXObject form && hasGraphics(form, form.getResources() == null ? resources : form.getResources(), depth + 1)) return true;
                }
            }
            previous = token;
        }
        return false;
    }
    private Rectangle inkBounds(BufferedImage image) {
        int left = image.getWidth(), right = -1, top = image.getHeight(), bottom = -1;
        for (int y = 0; y < image.getHeight(); y++) for (int x = 0; x < image.getWidth(); x++) {
            int pixel = image.getRGB(x, y);
            if (((pixel >>> 16) & 255) < 250 || ((pixel >>> 8) & 255) < 250 || (pixel & 255) < 250) {
                left = Math.min(left, x); right = Math.max(right, x); top = Math.min(top, y); bottom = Math.max(bottom, y);
            }
        }
        return right < left ? null : new Rectangle(left, top, right - left + 1, bottom - top + 1);
    }
    private Rectangle cropBounds(BufferedImage image) {
        Rectangle full = new Rectangle(0, 0, image.getWidth(), image.getHeight()), ink = inkBounds(image);
        if (ink == null) return full;
        int padding = Math.max(20, Math.min(image.getWidth(), image.getHeight()) / 50);
        ink.grow(padding, padding); ink = ink.intersection(full);
        return (long) ink.width * ink.height <= (long) full.width * full.height * .85 ? ink : full;
    }
    private byte[] jpeg(BufferedImage picture, Rectangle bounds) throws IOException {
        BufferedImage rgb = new BufferedImage(bounds.width, bounds.height, BufferedImage.TYPE_INT_RGB);
        var graphics = rgb.createGraphics();
        try { graphics.setColor(Color.WHITE); graphics.fillRect(0, 0, bounds.width, bounds.height); graphics.drawImage(picture, -bounds.x, -bounds.y, null); }
        finally { graphics.dispose(); }
        ImageWriter writer = ImageIO.getImageWritersByFormatName("jpeg").next();
        try (ByteArrayOutputStream buffer = new ByteArrayOutputStream(); var output = new MemoryCacheImageOutputStream(buffer)) {
            writer.setOutput(output); var options = writer.getDefaultWriteParam();
            options.setCompressionMode(ImageWriteParam.MODE_EXPLICIT); options.setCompressionQuality(.88f);
            writer.write(null, new IIOImage(rgb, null, null), options); output.flush(); return buffer.toByteArray();
        } finally { writer.dispose(); rgb.flush(); }
    }
}
