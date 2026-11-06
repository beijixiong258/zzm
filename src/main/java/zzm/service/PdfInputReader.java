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
import org.apache.pdfbox.cos.COSName;
import org.apache.pdfbox.cos.COSNumber;
import org.apache.pdfbox.pdfparser.PDFStreamParser;
import org.apache.pdfbox.pdmodel.*;
import org.apache.pdfbox.pdmodel.graphics.form.PDFormXObject;
import org.apache.pdfbox.pdmodel.graphics.image.PDImageXObject;
import org.apache.pdfbox.pdmodel.interactive.annotation.PDAnnotationLink;
import org.apache.pdfbox.pdmodel.interactive.annotation.PDAnnotationPopup;
import org.apache.pdfbox.rendering.PDFRenderer;
import org.apache.pdfbox.text.PDFTextStripper;
import org.springframework.stereotype.Component;
import javax.imageio.*;
import javax.imageio.stream.MemoryCacheImageOutputStream;
import java.awt.Color;
import java.awt.Rectangle;
import java.awt.geom.Path2D;
import java.awt.geom.Rectangle2D;
import java.awt.image.BufferedImage;
import java.io.*;
import java.nio.file.Path;
import java.util.*;
import java.util.function.BiConsumer;
import java.util.function.Consumer;
import static zzm.exception.ApiErrors.error;

/** 仅在本机准备 PDF 材料，不依赖模型或执行转录。 */
@Slf4j
@Component
@RequiredArgsConstructor
public class PdfInputReader {
    private final AppProperties properties;
    private final ContextBudget budget;

    public record SearchPage(String text, byte[] image) {}

    /** 检索表示单独读取原生文字和必要原图，不改变教师生成所用的整份 PDF 输入模式。 */
    public SearchPage searchPage(CourseMaterial material, int pageNumber) {
        try (PDDocument document = Loader.loadPDF(properties.uploadPath(material.getStoragePath()).toFile())) {
            if (pageNumber < 1 || pageNumber > document.getNumberOfPages()) throw error(422, "Page not found");
            String text = "";
            if (document.getCurrentAccessPermission().canExtractContent()) {
                PDFTextStripper stripper = new PDFTextStripper(); stripper.setSortByPosition(true);
                stripper.setStartPage(pageNumber); stripper.setEndPage(pageNumber); text = stripper.getText(document).strip();
            }
            PDPage page = document.getPage(pageNumber - 1);
            // 混排页保留文字层，同时为图中独有的公式、标签和关系准备页面图像。
            String nativeText = usableText(text) ? text : "";
            boolean visual = nativeText.isBlank() || hasGraphics(page, page.getResources(), 0, true)
                || page.getAnnotations().stream().anyMatch(a -> !a.isInvisible() && !a.isHidden() && !a.isNoView()
                    && !(a instanceof PDAnnotationLink) && !(a instanceof PDAnnotationPopup));
            return new SearchPage(nativeText, visual ? renderPage(document, pageNumber) : null);
        } catch (IOException exception) { throw error(422, "The PDF page could not be read"); }
    }
    /** 学生对话只渲染指定页；不调用遍历全部页面的生成入口。 */
    public byte[] image(CourseMaterial material, int pageNumber) {
        try (PDDocument document = Loader.loadPDF(properties.uploadPath(material.getStoragePath()).toFile())) {
            if (pageNumber < 1 || pageNumber > document.getNumberOfPages()) throw error(422, "Page not found");
            return renderPage(document, pageNumber);
        } catch (IOException exception) { throw error(422, "The PDF page could not be read"); }
    }
    private byte[] renderPage(PDDocument document, int pageNumber) throws IOException {
        PDFRenderer renderer = new PDFRenderer(document); renderer.setSubsamplingAllowed(true);
        BufferedImage picture = renderer.renderImageWithDPI(pageNumber - 1, dpi(document.getPage(pageNumber - 1)));
        try { return jpeg(picture, cropBounds(picture)); }
        finally { picture.flush(); }
    }

    public static boolean isPdf(CourseMaterial material) {
        return material.hasPdfFormat();
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
                    // 纯文本提取无法完整保留图形和批注。
                    if (!usableText(text) || hasGraphics(document.getPage(i), document.getPage(i).getResources(), 0, false)
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
            // 空文档也按完整页序保留页面图像。
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
    /** 仅在完整请求通过用量校验后，才按准备好的页面尺寸重新生成图像。 */
    public void images(CourseMaterial material, BiConsumer<PageInput, byte[]> consume) {
        Report report = report(material);
        if (!complete(report) || !"images".equals(report.getPdfInputMode()))
            throw error(422, "Reprocess the PDF with the current document parser before continuing.");
        try (PDDocument document = Loader.loadPDF(properties.uploadPath(material.getStoragePath()).toFile())) {
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
    private boolean hasGraphics(PDContentStream stream, PDResources resources, int depth, boolean skipRules) throws IOException {
        if (depth > 12) return true;
        List<Object> tokens = new PDFStreamParser(stream).parse();
        int pathStart = 0;
        int boxes = 0;
        int horizontalRules = 0, verticalRules = 0;
        for (int i = 0; i < tokens.size(); i++) {
            if (!(tokens.get(i) instanceof Operator operator)) continue;
            switch (operator.getName()) {
                case "BI", "sh" -> { return true; }
                case "Do" -> {
                    if (resources == null || i == 0 || !(tokens.get(i - 1) instanceof COSName name)) return true;
                    var object = resources.getXObject(name);
                    if (object instanceof PDImageXObject) return true;
                    if (object instanceof PDFormXObject form && hasGraphics(form,
                        form.getResources() == null ? resources : form.getResources(), depth + 1, skipRules)) return true;
                }
                case "S", "s", "f", "F", "f*", "B", "B*", "b", "b*" -> {
                    if (!skipRules) return true;
                    var shape = simplePath(tokens, pathStart, i);
                    if (shape == null) return true;
                    Rectangle2D bounds = shape.getBounds2D();
                    double width = bounds.getWidth(), height = bounds.getHeight();
                    if (width > 0 && height > 0 && !shape.contains(bounds)) return true;
                    double thickness = Math.min(width, height);
                    if (thickness <= 2 && Math.max(width, height) >= 8 * thickness) {
                        if (width > height) horizontalRules++;
                        if (height > width) verticalRules++;
                        // 同时出现横纵边界和内部划线，可能是需要保留行列关系的表格。
                        if (horizontalRules >= 3 && verticalRules >= 3) return true;
                    } else {
                        boolean outline = "S".equals(operator.getName()) || "s".equals(operator.getName());
                        boolean pageBackground = stream instanceof PDPage p && bounds.contains(p.getCropBox().getLowerLeftX(),
                            p.getCropBox().getLowerLeftY(), p.getCropBox().getWidth(), p.getCropBox().getHeight());
                        if (!outline && !pageBackground) return true;
                        if (outline && ++boxes > 1) return true;
                    }
                    pathStart = i + 1;
                }
                case "n" -> pathStart = i + 1;
            }
        }
        return false;
    }
    /** 只把一条轴对齐线或一个独立矩形视为装饰；曲线、组合路径和无法判读的路径保守地保留。 */
    private Path2D simplePath(List<Object> tokens, int start, int end) {
        Path2D.Double path = new Path2D.Double();
        int points = 0;
        for (int i = start; i < end; i++) {
            if (!(tokens.get(i) instanceof Operator operator)) continue;
            switch (operator.getName()) {
                case "re" -> {
                    if (points != 0 || i < 4) return null;
                    if (!(tokens.get(i - 4) instanceof COSNumber x) || !(tokens.get(i - 3) instanceof COSNumber y)
                        || !(tokens.get(i - 2) instanceof COSNumber w) || !(tokens.get(i - 1) instanceof COSNumber h)) return null;
                    double x0 = x.floatValue(), y0 = y.floatValue(), x1 = x0 + w.floatValue(), y1 = y0 + h.floatValue();
                    path.append(new Rectangle2D.Double(Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0)), false);
                    points = 5;
                }
                case "m", "l" -> {
                    if (++points > 5 || i < 2 || !(tokens.get(i - 2) instanceof COSNumber x)
                        || !(tokens.get(i - 1) instanceof COSNumber y)) return null;
                    if ("m".equals(operator.getName()) && points == 1) path.moveTo(x.floatValue(), y.floatValue());
                    else if ("l".equals(operator.getName()) && points > 1) path.lineTo(x.floatValue(), y.floatValue());
                    else return null;
                }
                case "h" -> { if (points > 0) path.closePath(); }
                case "c", "v", "y" -> { return null; }
                case "cm" -> { if (points > 0) return null; }
            }
        }
        return path;
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
