package cn.aicademiya.service;

import cn.aicademiya.config.AppProperties;
import cn.aicademiya.dto.DocumentExtraction;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.contentstream.operator.Operator;
import org.apache.pdfbox.pdfparser.PDFStreamParser;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.rendering.PDFRenderer;
import org.apache.pdfbox.text.PDFTextStripper;
import org.apache.poi.hwpf.HWPFDocument;
import org.apache.poi.hwpf.extractor.WordExtractor;
import org.apache.poi.openxml4j.opc.OPCPackage;
import org.apache.poi.openxml4j.opc.PackageAccess;
import org.apache.poi.sl.usermodel.Shape;
import org.apache.poi.sl.usermodel.ShapeContainer;
import org.apache.poi.sl.usermodel.Slide;
import org.apache.poi.sl.usermodel.SlideShow;
import org.apache.poi.sl.usermodel.SlideShowFactory;
import org.apache.poi.sl.usermodel.TableShape;
import org.apache.poi.sl.usermodel.TextShape;
import org.apache.poi.ss.usermodel.*;
import org.apache.poi.xwpf.extractor.XWPFWordExtractor;
import org.apache.poi.xwpf.usermodel.XWPFDocument;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;
import org.w3c.dom.Node;
import javax.imageio.*;
import javax.imageio.stream.MemoryCacheImageInputStream;
import javax.imageio.stream.MemoryCacheImageOutputStream;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.*;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import java.awt.Color;
import java.awt.Dimension;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.charset.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.Callable;
import java.util.function.Consumer;
import java.util.zip.ZipFile;

@Slf4j
@Component
@RequiredArgsConstructor
public class DocumentParser {
    private final AppProperties properties;
    private final AiService ai;

    public DocumentExtraction parse(Path source, String fileName, Consumer<DocumentExtraction.Report> progress) {
        Context context = new Context(progress, Math.max(1, properties.getDocumentMaxUnits()),
            Math.max(1000, properties.getDocumentMaxCharacters()));
        String extension = fileName.substring(fileName.lastIndexOf('.') + 1).toLowerCase(Locale.ROOT);
        try {
            switch (extension) {
                case "pdf" -> pdf(source, context);
                case "docx" -> docx(source, context);
                case "doc" -> doc(source, context);
                case "pptx", "ppt" -> slides(source, context);
                case "xlsx", "xls" -> workbook(source, context);
                case "txt", "md" -> {
                    context.total(1);
                    unit(context, "Document text", () -> decodeText(Files.readAllBytes(source)));
                }
                case "png", "jpg", "jpeg", "webp" -> {
                    context.total(1);
                    unit(context, "Image 1", () -> image(context, "Image 1",
                        Files.readAllBytes(source), extension.equals("webp") ? "image/webp" : ""));
                }
                default -> throw new IOException("Unsupported document type");
            }
            if (Set.of("docx", "pptx", "xlsx").contains(extension) && context.available()) {
                officeParts(source, extension.equals("docx"), context);
            }
        } catch (Exception exception) {
            log.warn("Document format processing failed ({})", exception.getClass().getSimpleName());
            context.fail("Document", "The document could not be fully opened. Check for encryption, damage or unsupported embedded content.");
        }
        return context.finish();
    }

    private void pdf(Path source, Context context) throws IOException {
        try (PDDocument document = Loader.loadPDF(source.toFile())) {
            if (!document.getCurrentAccessPermission().canExtractContent()) {
                throw new IOException("PDF extraction is restricted");
            }
            context.total(document.getNumberOfPages());
            PDFRenderer renderer = new PDFRenderer(document);
            renderer.setSubsamplingAllowed(true);
            PDFTextStripper stripper = new PDFTextStripper();
            stripper.setSortByPosition(true);
            for (int index = 0; index < document.getNumberOfPages() && context.available(); index++) {
                int pageIndex = index;
                String label = "Page " + (index + 1);
                unit(context, label, () -> {
                    stripper.setStartPage(pageIndex + 1);
                    stripper.setEndPage(pageIndex + 1);
                    String text = stripper.getText(document);
                    PDPage page = document.getPage(pageIndex);
                    if (!needsVision(page, text)) return text;
                    double edge = Math.max(page.getCropBox().getWidth(), page.getCropBox().getHeight());
                    if (!Double.isFinite(edge) || edge <= 0) throw new IOException("Invalid PDF page size");
                    float dpi = (float) Math.min(144, imageMaxEdge() * 72.0 / edge);
                    try {
                        return visual(context, label, renderer.renderImageWithDPI(pageIndex, dpi), text);
                    } catch (Exception exception) {
                        context.append(label + " — text", text);
                        throw exception;
                    }
                });
            }
        }
    }

    private boolean needsVision(PDPage page, String text) throws IOException {
        // Text extraction alone cannot preserve diagrams, outlined glyphs or formula layout.
        if (text.strip().length() < 80 || text.indexOf('\uFFFD') >= 0
            || text.matches("(?s).*[=∑∫√∂≤≥∞∈⊂⊆].*")) return true;
        if (page.getResources() != null && page.getResources().getXObjectNames().iterator().hasNext()) return true;
        for (Object token : new PDFStreamParser(page).parse()) {
            if (token instanceof Operator operator && Set.of("S", "s", "f", "F", "f*", "B", "B*", "b", "b*", "sh").contains(operator.getName())) return true;
        }
        return false;
    }

    private void docx(Path source, Context context) throws Exception {
        try (OPCPackage archive = OPCPackage.open(source.toFile(), PackageAccess.READ);
             XWPFDocument document = new XWPFDocument(archive)) {
            var pictures = document.getAllPackagePictures();
            context.total(1 + pictures.size());
            context.report.setVisualReviewRequired(true);
            context.note("Office text, tables and images are extracted separately; compare their placement with the original.");
            unit(context, "Document text", () -> new XWPFWordExtractor(document).getText());
            for (int index = 0; index < pictures.size() && context.available(); index++) {
                var picture = pictures.get(index);
                String label = "Image " + (index + 1);
                unit(context, label, () -> image(context, label, picture.getData(), picture.getPackagePart().getContentType()));
            }
        }
    }

    private void doc(Path source, Context context) throws Exception {
        try (InputStream input = Files.newInputStream(source); HWPFDocument document = new HWPFDocument(input)) {
            var pictures = document.getPicturesTable().getAllPictures();
            context.total(1 + pictures.size());
            context.report.setVisualReviewRequired(true);
            context.note("Legacy Word layout and embedded objects may need a PDF export for complete interpretation.");
            unit(context, "Document text", () -> new WordExtractor(document).getText());
            for (int index = 0; index < pictures.size() && context.available(); index++) {
                var picture = pictures.get(index);
                String label = "Image " + (index + 1);
                unit(context, label, () -> image(context, label, picture.getContent(), picture.getMimeType()));
            }
        }
    }

    private void slides(Path source, Context context) throws Exception {
        try (SlideShow<?, ?> show = SlideShowFactory.create(source.toFile(), null, true)) {
            context.total(show.getSlides().size());
            context.report.setVisualReviewRequired(true);
            context.note("Slide rendering may substitute fonts; compare diagrams and symbols with the original.");
            for (int index = 0; index < show.getSlides().size() && context.available(); index++) {
                Slide<?, ?> slide = show.getSlides().get(index);
                String label = "Slide " + (index + 1);
                unit(context, label, () -> {
                    String text = shapeText(slide);
                    if (slide.getNotes() != null) text += "\n\nSpeaker notes:\n" + shapeText(slide.getNotes());
                    try {
                        BufferedImage canvas = slideImage(slide, show.getPageSize());
                        return visual(context, label, canvas, text);
                    } catch (Exception exception) {
                        context.append(label + " — text", text);
                        throw exception;
                    }
                });
            }
        }
    }

    private String shapeText(ShapeContainer<?, ?> container) {
        StringBuilder text = new StringBuilder();
        for (Shape<?, ?> shape : container.getShapes()) {
            if (shape instanceof TextShape<?, ?> textShape) text.append(textShape.getText()).append('\n');
            else if (shape instanceof TableShape<?, ?> table) {
                for (int row = 0; row < table.getNumberOfRows(); row++) {
                    for (int column = 0; column < table.getNumberOfColumns(); column++) {
                        var cell = table.getCell(row, column);
                        text.append(cell == null ? "" : cell.getText()).append('\t');
                    }
                    text.append('\n');
                }
            } else if (shape instanceof ShapeContainer<?, ?> group) text.append(shapeText(group));
        }
        return text.toString();
    }

    private BufferedImage slideImage(Slide<?, ?> slide, Dimension size) throws IOException {
        if (size.width <= 0 || size.height <= 0) throw new IOException("Invalid slide size");
        double scale = Math.min(2, (double) imageMaxEdge() / Math.max(size.width, size.height));
        BufferedImage image = new BufferedImage(Math.max(1, (int) (size.width * scale)),
            Math.max(1, (int) (size.height * scale)), BufferedImage.TYPE_INT_RGB);
        Graphics2D graphics = image.createGraphics();
        try {
            graphics.setColor(Color.WHITE);
            graphics.fillRect(0, 0, image.getWidth(), image.getHeight());
            graphics.scale(scale, scale);
            graphics.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
            graphics.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON);
            slide.draw(graphics);
            return image;
        } catch (RuntimeException exception) {
            image.flush();
            throw exception;
        } finally {
            graphics.dispose();
        }
    }

    private void workbook(Path source, Context context) throws Exception {
        try (Workbook workbook = WorkbookFactory.create(source.toFile(), null, true)) {
            var pictures = workbook.getAllPictures();
            context.total(workbook.getNumberOfSheets() + pictures.size());
            context.report.setVisualReviewRequired(true);
            context.note("Spreadsheet values use saved formula results; formulas are retained and external links are not recalculated.");
            DataFormatter formatter = new DataFormatter(Locale.ROOT);
            formatter.setUseCachedValuesForFormulaCells(true);
            for (int index = 0; index < workbook.getNumberOfSheets() && context.available(); index++) {
                Sheet sheet = workbook.getSheetAt(index);
                unit(context, "Sheet " + (index + 1), () -> {
                    StringBuilder text = new StringBuilder(sheet.getSheetName()).append('\n');
                    int cellCount = 0;
                    outer: for (Row row : sheet) {
                        for (Cell cell : row) {
                            if (++cellCount > 100000 || text.length() >= context.remaining()) {
                                context.truncate();
                                break outer;
                            }
                            String value = formatter.formatCellValue(cell);
                            if (value.isBlank() && cell.getCellType() != CellType.FORMULA) continue;
                            text.append(cell.getAddress()).append(": ").append(value);
                            if (cell.getCellType() == CellType.FORMULA) text.append(" [=").append(cell.getCellFormula()).append(']');
                            text.append('\n');
                        }
                    }
                    return text.toString();
                });
            }
            for (int index = 0; index < pictures.size() && context.available(); index++) {
                var picture = pictures.get(index);
                String label = "Image " + (index + 1);
                unit(context, label, () -> image(context, label, picture.getData(), picture.getMimeType()));
            }
        }
    }

    private void officeParts(Path source, boolean word, Context context) throws Exception {
        // Keep chart data and equation structure that the plain-text Office extractors omit.
        try (ZipFile archive = new ZipFile(source.toFile())) {
            var entries = archive.stream().filter(entry -> entry.getName().matches(
                "(word|ppt|xl)/(charts/chart[0-9]+|diagrams/data[0-9]+)\\.xml")).toList();
            context.total(context.report.getUnitsTotal() + entries.size());
            for (int index = 0; index < entries.size() && context.available(); index++) {
                var entry = entries.get(index);
                unit(context, "Office graphic " + (index + 1), () -> {
                    try (InputStream input = archive.getInputStream(entry)) {
                        String xml = readXml(input, context.maxCharacters);
                        return "Office chart or diagram source (OOXML):\n" + xml;
                    }
                });
            }
            if (!word || !context.available()) return;
            var body = archive.getEntry("word/document.xml");
            if (body == null) throw new IOException("Word document body is missing");
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            factory.setNamespaceAware(true);
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
            try (InputStream input = archive.getInputStream(body)) {
                byte[] bytes = input.readNBytes(16 * 1024 * 1024 + 1);
                if (bytes.length > 16 * 1024 * 1024) { context.truncate(); return; }
                var document = factory.newDocumentBuilder().parse(new ByteArrayInputStream(bytes));
                var equations = document.getElementsByTagNameNS(
                    "*", "oMath");
                var textBoxes = document.getElementsByTagNameNS(
                    "*", "txbxContent");
                context.total(context.report.getUnitsTotal() + equations.getLength() + textBoxes.getLength());
                for (int index = 0; index < equations.getLength() && context.available(); index++) {
                    Node equation = equations.item(index);
                    unit(context, "Equation " + (index + 1), () -> "Office equation source (OMML):\n" + xml(equation));
                }
                for (int index = 0; index < textBoxes.getLength() && context.available(); index++) {
                    Node textBox = textBoxes.item(index);
                    unit(context, "Text box " + (index + 1), () -> "Office text box source:\n" + xml(textBox));
                }
            }
        }
    }

    private String xml(Node node) throws TransformerException {
        TransformerFactory factory = TransformerFactory.newInstance();
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");
        Transformer transformer = factory.newTransformer();
        transformer.setOutputProperty(OutputKeys.OMIT_XML_DECLARATION, "yes");
        StringWriter output = new StringWriter();
        transformer.transform(new DOMSource(node), new StreamResult(output));
        return output.toString();
    }

    private String readXml(InputStream input, int limit) throws IOException {
        byte[] bytes = input.readNBytes(limit * 4 + 1);
        if (bytes.length > limit * 4) throw new IOException("Office graphic exceeds extraction limit");
        return decodeText(bytes);
    }

    private String image(Context context, String label, byte[] bytes, String mimeType) throws Exception {
        try (var input = new MemoryCacheImageInputStream(new ByteArrayInputStream(bytes))) {
            var readers = ImageIO.getImageReaders(input);
            if (!readers.hasNext()) {
                if ("image/webp".equals(mimeType) && bytes.length >= 12
                    && new String(bytes, 0, 4, StandardCharsets.US_ASCII).equals("RIFF")
                    && new String(bytes, 8, 4, StandardCharsets.US_ASCII).equals("WEBP")) {
                    return recognize(context, label, bytes, "image/webp", "");
                }
                context.note("An embedded image format could not be decoded. Export the document to PDF and upload it again.");
                throw new IOException("Unsupported image encoding");
            }
            ImageReader reader = readers.next();
            try {
                reader.setInput(input);
                int edge = Math.max(reader.getWidth(0), reader.getHeight(0));
                ImageReadParam options = reader.getDefaultReadParam();
                int sample = Math.max(1, (int) Math.ceil((double) edge / imageMaxEdge()));
                options.setSourceSubsampling(sample, sample, 0, 0);
                return visual(context, label, reader.read(0, options), "");
            } finally {
                reader.dispose();
            }
        }
    }

    private String visual(Context context, String label, BufferedImage image, String extractedText) throws Exception {
        BufferedImage rgb = new BufferedImage(image.getWidth(), image.getHeight(), BufferedImage.TYPE_INT_RGB);
        Graphics2D graphics = rgb.createGraphics();
        try {
            graphics.setColor(Color.WHITE);
            graphics.fillRect(0, 0, rgb.getWidth(), rgb.getHeight());
            graphics.drawImage(image, 0, 0, null);
        } finally {
            graphics.dispose();
            image.flush();
        }
        byte[] bytes;
        ImageWriter writer = ImageIO.getImageWritersByFormatName("jpeg").next();
        try (ByteArrayOutputStream buffer = new ByteArrayOutputStream();
             var output = new MemoryCacheImageOutputStream(buffer)) {
            writer.setOutput(output);
            ImageWriteParam options = writer.getDefaultWriteParam();
            options.setCompressionMode(ImageWriteParam.MODE_EXPLICIT);
            options.setCompressionQuality(0.88f);
            writer.write(null, new IIOImage(rgb, null, null), options);
            output.flush();
            bytes = buffer.toByteArray();
        } finally {
            writer.dispose();
            rgb.flush();
        }
        return recognize(context, label, bytes, "image/jpeg", extractedText);
    }

    private String recognize(Context context, String label, byte[] image, String mimeType, String extractedText) {
        var reading = ai.readVisual(label, image, mimeType, extractedText);
        context.report.setVisualReviewRequired(true);
        context.report.setVisionUnits(context.report.getVisionUnits() + 1);
        if (!reading.isReadable() || !reading.getIssues().isEmpty()) {
            context.append(label + " — partial", reading.getText());
            throw new IllegalStateException("Image content is incomplete");
        }
        return reading.getText();
    }

    private int imageMaxEdge() {
        return Math.max(1000, Math.min(3000, properties.getDocumentImageMaxEdge()));
    }


    private String decodeText(byte[] bytes) throws CharacterCodingException {
        if (bytes.length >= 2 && bytes[0] == (byte) 0xFF && bytes[1] == (byte) 0xFE) return new String(bytes, 2, bytes.length - 2, StandardCharsets.UTF_16LE);
        if (bytes.length >= 2 && bytes[0] == (byte) 0xFE && bytes[1] == (byte) 0xFF) return new String(bytes, 2, bytes.length - 2, StandardCharsets.UTF_16BE);
        try {
            return StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes)).toString().replace("\uFEFF", "");
        } catch (CharacterCodingException exception) {
            return Charset.forName("GB18030").newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes)).toString();
        }
    }

    private void unit(Context context, String label, Callable<String> reader) {
        if (!context.available()) return;
        context.attempted++;
        try {
            if (Thread.currentThread().isInterrupted()) throw new InterruptedException();
            context.append(label, reader.call());
            context.report.setUnitsProcessed(context.report.getUnitsProcessed() + 1);
            context.consecutiveFailures = 0;
        } catch (Exception exception) {
            context.consecutiveFailures++;
            if (exception instanceof ResponseStatusException status && status.getReason() != null) context.note(status.getReason());
            if (exception instanceof InterruptedException) Thread.currentThread().interrupt();
            log.warn("Document unit {} could not be read ({})", label, exception.getClass().getSimpleName());
            context.fail(label, "Some document units could not be read. Check the original and retry processing.");
        }
        context.progress.accept(context.report);
    }

    private static final class Context {
        private final DocumentExtraction result = new DocumentExtraction();
        private final DocumentExtraction.Report report = result.getReport();
        private final StringBuilder text = new StringBuilder();
        private final Consumer<DocumentExtraction.Report> progress;
        private final int maxUnits;
        private final int maxCharacters;
        private int attempted;
        private int consecutiveFailures;

        private Context(Consumer<DocumentExtraction.Report> progress, int maxUnits, int maxCharacters) {
            this.progress = progress;
            this.maxUnits = maxUnits;
            this.maxCharacters = maxCharacters;
        }

        private void total(int total) { report.setUnitsTotal(total); progress.accept(report); }
        private int remaining() { return Math.max(0, maxCharacters - text.length()); }
        private void note(String note) { if (!report.getNotes().contains(note)) report.getNotes().add(note); }
        private void truncate() {
            report.setTruncated(true);
            note("The document exceeds the processing limit. Split it into smaller files and upload them again.");
        }
        private boolean available() {
            if (consecutiveFailures >= 3) { note("Processing stopped after repeated failures; remaining units were not read."); return false; }
            if (Thread.currentThread().isInterrupted()) { fail("Document", "Document processing was interrupted. Retry when ready."); return false; }
            if (attempted >= maxUnits || remaining() == 0) { truncate(); return false; }
            return true;
        }
        private void append(String label, String value) {
            if (value == null || value.isBlank()) return;
            String chunk = "\n\n## " + label + "\n" + value.replace("\u0000", "").trim();
            int count = Math.min(remaining(), chunk.length());
            if (count < chunk.length()) truncate();
            // Avoid ending with one half of a UTF-16 surrogate pair.
            if (count > 0 && Character.isHighSurrogate(chunk.charAt(count - 1))) count--;
            text.append(chunk, 0, count);
        }
        private void fail(String label, String note) {
            if (!report.getFailedUnits().contains(label)) report.getFailedUnits().add(label);
            note(note);
        }
        private DocumentExtraction finish() {
            result.setText(text.toString().strip());
            if (result.getText().isBlank()) {
                result.setStatus("failed");
                result.setWarning("No readable content was extracted. Check the original file and retry.");
            } else if (!report.getFailedUnits().isEmpty() || report.isTruncated() || report.getUnitsProcessed() < report.getUnitsTotal()) {
                result.setStatus("needsReview");
                result.setWarning("Document processing is incomplete. Retry failed units or upload smaller files before generating a task.");
            } else {
                result.setStatus(report.isVisualReviewRequired() ? "needsReview" : "ready");
                result.setWarning(report.isVisualReviewRequired() ? "Check figures, handwriting and layout against the original." : "");
            }
            return result;
        }
    }
}
