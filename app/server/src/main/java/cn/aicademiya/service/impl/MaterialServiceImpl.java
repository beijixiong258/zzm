package cn.aicademiya.service.impl;

import cn.aicademiya.config.AppProperties;
import cn.aicademiya.dto.Requests;
import cn.aicademiya.dto.DocumentExtraction;
import cn.aicademiya.entity.*;
import cn.aicademiya.mapper.*;
import cn.aicademiya.service.*;
import cn.hutool.core.util.IdUtil;
import cn.hutool.json.*;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import java.io.IOException;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import static cn.aicademiya.exception.ApiErrors.error;

@Slf4j
@Service
@RequiredArgsConstructor
public class MaterialServiceImpl extends ServiceImpl<CourseMaterialMapper, CourseMaterial> implements MaterialService {
    private final CourseService courses;
    private final AppProperties properties;
    private final DocumentParser parser;
    private final PdfInputReader pdf;
    private final SessionVersionMapper versions;
    private final TeachingSessionMapper sessions;
    private final LearningRecordMapper records;
    @Override public List<Map<String, Object>> library(String courseId, AccountUser user) {
        courses.requireAccess(courseId, user, true);
        return lambdaQuery().eq(CourseMaterial::getCourseId, courseId).isNull(CourseMaterial::getOwnerId).orderByAsc(CourseMaterial::getRelativePath).list().stream().map(this::view).toList();
    }
    @Override public CourseMaterial upload(String courseId, MultipartFile file, String relativePath, String visibility, AccountUser user) {
        courses.requireAccess(courseId, user, true);
        return store(courseId, file, relativePath, visibility, null, null, null);
    }
    @Override public CourseMaterial uploadForRecord(String courseId, String recordId, String questionId, MultipartFile file, AccountUser user) {
        // LearningService holds the record row lock across this check and the insert.
        List<CourseMaterial> active = lambdaQuery().eq(CourseMaterial::getRecordId, recordId).eq(CourseMaterial::getArchived, false).list();
        if (active.size() >= 100) throw error(422, "This learning record has reached its attachment limit");
        long bytes = 0;
        for (CourseMaterial item : active) bytes = Math.addExact(bytes, fileSize(item));
        if (file.getSize() > Math.max(0, properties.getAttachmentMaxBytes() - bytes))
            throw error(422, "This learning record has reached its total attachment size limit. Remove unused attachments before uploading.");
        return store(courseId, file, "", "student", user.getId(), recordId, questionId);
    }
    private long fileSize(CourseMaterial material) {
        if (material.getFileSize() != null) return material.getFileSize();
        try {
            long size = Files.size(Path.of(material.getStoragePath()));
            lambdaUpdate().eq(CourseMaterial::getId, material.getId()).isNull(CourseMaterial::getFileSize).set(CourseMaterial::getFileSize, size).update();
            return size;
        } catch (IOException exception) { throw error(409, "An existing attachment is unavailable. Remove it before uploading more files."); }
    }
    private CourseMaterial store(String courseId, MultipartFile file, String relativePath, String visibility, String ownerId, String recordId, String questionId) {
        if (!Set.of("student", "teacher").contains(visibility) || file.isEmpty() || file.getSize() > 25L * 1024 * 1024) throw error(422, "Invalid file or visibility");
        String name = Objects.requireNonNullElse(file.getOriginalFilename(), "material").replace('\\', '/');
        name = name.substring(name.lastIndexOf('/') + 1);
        if (name.isBlank() || name.length() > 255) throw error(422, "Invalid file name");
        String extension = name.contains(".") ? name.substring(name.lastIndexOf('.')).toLowerCase(Locale.ROOT) : "";
        if (!Set.of(".pdf", ".epub", ".docx", ".doc", ".pptx", ".txt", ".md", ".xlsx", ".png", ".jpg", ".jpeg", ".webp", ".ppt", ".xls").contains(extension)) throw error(422, "Unsupported file type");
        String sourcePath = relativePath == null || relativePath.isBlank() ? name : relativePath.replace('\\', '/');
        if (sourcePath.length() > 1024 || sourcePath.startsWith("/") || sourcePath.contains(":") || Arrays.asList(sourcePath.split("/")).contains("..")) throw error(422, "Invalid folder path");
        CourseMaterial material = new CourseMaterial(); material.setId(IdUtil.fastSimpleUUID());
        Path destination = Path.of(properties.getUploadDir()).toAbsolutePath().normalize().resolve(material.getId() + extension);
        try { Files.createDirectories(destination.getParent()); file.transferTo(destination); }
        catch (IOException exception) { recycleUncommitted(destination); throw error(500, "File could not be saved"); }
        material.setCourseId(courseId); material.setOwnerId(ownerId); material.setRecordId(recordId); material.setQuestionId(questionId); material.setTitle(name); material.setFileName(name); material.setRelativePath(sourcePath);
        material.setMimeType(switch (extension) { case ".epub" -> "application/epub+zip"; case ".pdf" -> "application/pdf"; case ".docx" -> "application/vnd.openxmlformats-officedocument.wordprocessingml.document"; case ".doc" -> "application/msword"; case ".pptx" -> "application/vnd.openxmlformats-officedocument.presentationml.presentation"; case ".ppt" -> "application/vnd.ms-powerpoint"; case ".xlsx" -> "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"; case ".xls" -> "application/vnd.ms-excel"; case ".txt", ".md" -> "text/plain"; case ".png" -> "image/png"; case ".jpg", ".jpeg" -> "image/jpeg"; case ".webp" -> "image/webp"; default -> "application/octet-stream"; });
        material.setStoragePath(destination.toString()); material.setVisibility(visibility); material.setStatus("queued");
        material.setTextContent(""); material.setErrorMessage(""); material.setArchived(false); material.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC));
        material.setFileSize(file.getSize());
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override public void afterCompletion(int status) {
                    if (status == STATUS_ROLLED_BACK) recycleUncommitted(destination);
                }
            });
        }
        try { save(material); } catch (RuntimeException exception) {
            if (!TransactionSynchronizationManager.isSynchronizationActive()) recycleUncommitted(destination);
            throw exception;
        }
        return material;
    }
    @Override public CourseMaterial requireFile(String id, String versionId, AccountUser user) {
        CourseMaterial material = getById(id);
        if (material == null) throw error(404, "Material not found");
        courses.requireAccess(material.getCourseId(), user, !"student".equals(user.getRole()));
        if (material.getOwnerId() != null) {
            if (!material.getOwnerId().equals(user.getId()) && "student".equals(user.getRole())) throw error(403, "Attachment access denied");
            if (Boolean.TRUE.equals(material.getArchived())) throw error(410, "This attachment has been removed.");
            return material;
        }
        if (!"student".equals(user.getRole())) return material;
        if (versionId == null) throw error(403, "A published task version is required");
        SessionVersion version = versions.selectById(versionId);
        if (version == null || !version.getCourseId().equals(material.getCourseId())) throw error(403, "Material access denied");
        TeachingSession session = sessions.selectById(version.getSessionId());
        boolean current = session != null && !Boolean.TRUE.equals(session.getArchived()) && versionId.equals(session.getPublishedVersionId());
        boolean studied = records.selectCount(Wrappers.<LearningRecord>lambdaQuery().eq(LearningRecord::getVersionId, versionId).eq(LearningRecord::getUserId, user.getId())) > 0;
        if (!current && !studied) throw error(403, "Material access denied");
        JSONArray snapshotMaterials = JSONUtil.parseObj(version.getContentJson()).getJSONArray("materials");
        boolean allowed = snapshotMaterials != null && snapshotMaterials.stream().map(JSONUtil::parseObj)
            .anyMatch(m -> id.equals(m.getStr("id")) && "student".equals(m.getStr("visibility")));
        if (!allowed) throw error(403, "Material access denied");
        return material;
    }
    @Override public void edit(String id, Requests.MaterialInput input, AccountUser user) {
        CourseMaterial material = requireFile(id, null, user); courses.requireAccess(material.getCourseId(), user, true);
        lambdaUpdate().eq(CourseMaterial::getId, id).set(CourseMaterial::getTitle, input.getTitle().trim()).set(CourseMaterial::getVisibility, input.getVisibility()).update();
    }
    @Override public void archive(String id, boolean archived, AccountUser user) {
        CourseMaterial material = requireFile(id, null, user); courses.requireAccess(material.getCourseId(), user, true);
        lambdaUpdate().eq(CourseMaterial::getId, id).set(CourseMaterial::getArchived, archived).update();
    }
    @Override public void retry(String id, AccountUser user) {
        CourseMaterial material = requireFile(id, null, user);
        if ("student".equals(user.getRole())) {
            LearningRecord record = material.getRecordId() == null ? null : records.selectById(material.getRecordId());
            if (record == null || !user.getId().equals(record.getUserId()) || Set.of("submitted","confirmed").contains(record.getStatus())) throw error(403,"This attachment cannot be changed");
        } else courses.requireAccess(material.getCourseId(), user, true);
        if ("processing".equals(material.getStatus())) throw error(409, "Material is processing");
        if (!lambdaUpdate().eq(CourseMaterial::getId, id).ne(CourseMaterial::getStatus, "processing")
            .set(CourseMaterial::getStatus, "queued").set(CourseMaterial::getErrorMessage, "")
            .set(CourseMaterial::getExtractionReportJson, null).set(CourseMaterial::getTextContent, "").update()) throw error(409, "Material is processing");
    }
    @Override public void recoverProcessing() {
        lambdaUpdate().eq(CourseMaterial::getStatus, "processing")
            .set(CourseMaterial::getStatus, "queued")
            .set(CourseMaterial::getErrorMessage, "Document processing was interrupted and has been queued again.").update();
    }

    @Override public void processNext() {
        List<CourseMaterial> queued = lambdaQuery().eq(CourseMaterial::getStatus, "queued")
            .eq(CourseMaterial::getArchived, false).orderByAsc(CourseMaterial::getCreatedAt)
            .page(new Page<CourseMaterial>(1, 1, false)).getRecords();
        if (queued.isEmpty()) return;
        CourseMaterial material = queued.get(0);
        if (!lambdaUpdate().eq(CourseMaterial::getId, material.getId()).eq(CourseMaterial::getStatus, "queued")
            .eq(CourseMaterial::getArchived, false).set(CourseMaterial::getStatus, "processing")
            .set(CourseMaterial::getTextContent, "").set(CourseMaterial::getErrorMessage, "").update()) return;
        try {
            Path source = Path.of(material.getStoragePath()).toAbsolutePath().normalize();
            if (!Files.isRegularFile(source)) throw new IOException("Original file is unavailable");
            DocumentExtraction result = parser.parse(source, material.getFileName(), report ->
                lambdaUpdate().eq(CourseMaterial::getId, material.getId()).eq(CourseMaterial::getStatus, "processing")
                    .set(CourseMaterial::getExtractionReportJson, JSONUtil.toJsonStr(report)).update());
            lambdaUpdate().eq(CourseMaterial::getId, material.getId()).eq(CourseMaterial::getStatus, "processing")
                .set(CourseMaterial::getStatus, result.getStatus()).set(CourseMaterial::getTextContent, result.getText())
                .set(CourseMaterial::getExtractionReportJson, JSONUtil.toJsonStr(result.getReport()))
                .set(CourseMaterial::getErrorMessage, result.getWarning()).update();
        } catch (Exception exception) {
            log.warn("Material {} processing failed ({})", material.getId(), exception.getClass().getSimpleName());
            lambdaUpdate().eq(CourseMaterial::getId, material.getId()).eq(CourseMaterial::getStatus, "processing")
                .set(CourseMaterial::getStatus, "failed")
                .set(CourseMaterial::getErrorMessage, "Document processing failed. Check the original file and model configuration, then retry.").update();
        }
    }

    private Path moveToRecycle(Path source, String category) throws IOException {
        Path uploadRoot = Path.of(properties.getUploadDir()).toAbsolutePath().normalize();
        Path trashRoot = properties.recycleRoot();
        source = source.toAbsolutePath().normalize();
        if (!source.startsWith(uploadRoot) || source.equals(uploadRoot) || trashRoot.startsWith(uploadRoot))
            throw new IOException("Unsafe recycling path");
        Path directory = trashRoot.resolve(category).normalize();
        Path destination = directory.resolve(source.getFileName()).normalize();
        if (!destination.startsWith(trashRoot) || Files.isSymbolicLink(source)) throw new IOException("Unsafe recycling path");
        Files.createDirectories(directory);
        if (!directory.toRealPath().startsWith(trashRoot.toRealPath())) throw new IOException("Unsafe recycling destination");
        if (Files.isRegularFile(source, LinkOption.NOFOLLOW_LINKS)) {
            if (!source.toRealPath().startsWith(uploadRoot.toRealPath())) throw new IOException("Unsafe source path");
            if (Files.exists(destination, LinkOption.NOFOLLOW_LINKS)) throw new FileAlreadyExistsException(destination.toString());
            try { Files.move(source, destination, StandardCopyOption.ATOMIC_MOVE); }
            catch (AtomicMoveNotSupportedException exception) { Files.move(source, destination); }
        }
        if (!Files.isRegularFile(destination, LinkOption.NOFOLLOW_LINKS)) throw new IOException("Recycled file is unavailable");
        return destination;
    }
    private void recycleUncommitted(Path source) {
        try { if (Files.exists(source)) moveToRecycle(source, "uncommitted-uploads"); }
        catch (IOException exception) { log.warn("Uncommitted upload could not be moved to the recycle directory: {}", source.getFileName()); }
    }
    @Override public synchronized void recycleRemovedAttachments() {
        List<CourseMaterial> removed = lambdaQuery().eq(CourseMaterial::getArchived, true).isNotNull(CourseMaterial::getOwnerId)
            .isNotNull(CourseMaterial::getFileRemovedAt).isNull(CourseMaterial::getTrashPath).ne(CourseMaterial::getStatus, "processing")
            .orderByAsc(CourseMaterial::getFileRemovedAt).page(new Page<CourseMaterial>(1, 50, false)).getRecords();
        for (CourseMaterial attachment : removed) {
            // Even archived references count: copied course materials may share physical storage.
            if (lambdaQuery().eq(CourseMaterial::getStoragePath, attachment.getStoragePath()).ne(CourseMaterial::getId, attachment.getId()).exists()) {
                log.warn("Attachment {} has shared storage; recycling skipped", attachment.getId()); continue;
            }
            try {
                Path destination = moveToRecycle(Path.of(attachment.getStoragePath()), "removed-attachments");
                if (attachment.getFileSize() != null && Files.size(destination) != attachment.getFileSize())
                    throw new IOException("Recycled file size differs from metadata");
                lambdaUpdate().eq(CourseMaterial::getId, attachment.getId()).eq(CourseMaterial::getArchived, true)
                    .isNull(CourseMaterial::getTrashPath).set(CourseMaterial::getTrashPath, destination.toString()).update();
            } catch (IOException | RuntimeException exception) {
                log.warn("Attachment {} could not be recycled ({}); the background job will retry", attachment.getId(), exception.getClass().getSimpleName());
            }
        }
    }
    @Override public void reportStorageUsage() {
        if (properties.getUploadWarningBytes() <= 0) return;
        long bytes = 0;
        for (Path directory : List.of(Path.of(properties.getUploadDir()).toAbsolutePath().normalize(), properties.recycleRoot())) {
            if (!Files.isDirectory(directory)) continue;
            try (var files = Files.walk(directory)) {
                bytes += files.filter(path -> Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)).mapToLong(path -> {
                    try { return Files.size(path); } catch (IOException exception) { return 0; }
                }).sum();
            } catch (IOException exception) { log.warn("Storage usage could not be measured for an application directory"); }
        }
        if (bytes >= properties.getUploadWarningBytes())
            log.warn("Application uploads and recycle storage total {} bytes, exceeding the configured warning threshold {}", bytes, properties.getUploadWarningBytes());
    }
    @Override public void requireProcessed(List<CourseMaterial> selected) {
        for (CourseMaterial material : selected) {
            if (!Set.of("ready", "needsReview").contains(material.getStatus()))
                throw error(422, "Select fully processed materials before continuing.");
            boolean imagePdf = false;
            if (PdfInputReader.isPdf(material)) {
                var pdfReport = pdf.report(material);
                if (!pdf.complete(pdfReport)) throw error(422, "Reprocess the PDF with the current document parser before continuing.");
                imagePdf = "images".equals(pdfReport.getPdfInputMode());
            }
            if (!imagePdf && Objects.toString(material.getTextContent(), "").isBlank())
                throw error(422, "Select processed materials with readable content");
            JSONObject report = material.getExtractionReportJson() == null ? new JSONObject() : JSONUtil.parseObj(material.getExtractionReportJson());
            if (report.getInt("schemaVersion", 0) < 2) {
                throw error(422, "Reprocess the selected materials with the current document parser before continuing.");
            }
            JSONArray failed = report.getJSONArray("failedUnits");
            if (failed == null || !failed.isEmpty() || report.getBool("truncated", true)
                || report.getInt("unitsTotal", 0) == 0 || !report.getInt("unitsTotal", 0).equals(report.getInt("unitsProcessed", -1))) {
                throw error(422, "Some selected materials are incomplete. Retry processing or select complete materials.");
            }
        }
    }
    @Override public List<CourseMaterial> selected(String courseId, List<String> ids) {
        if (ids == null || ids.isEmpty()) return List.of();
        List<CourseMaterial> result = lambdaQuery().eq(CourseMaterial::getCourseId, courseId).isNull(CourseMaterial::getOwnerId).in(CourseMaterial::getId, ids).eq(CourseMaterial::getArchived, false).list();
        if (result.size() != new HashSet<>(ids).size()) throw error(422, "Selected materials must belong to this course and be active");
        return result;
    }
    @Override public Map<String, Object> view(CourseMaterial material) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", material.getId()); result.put("title", material.getTitle()); result.put("fileName", material.getFileName());
        result.put("fileSize", material.getFileSize()); result.put("relativePath", material.getRelativePath()); result.put("mimeType", material.getMimeType()); result.put("status", material.getStatus());
        result.put("visibility", material.getVisibility()); result.put("errorMessage", material.getErrorMessage()); result.put("archived", material.getArchived());
        JSONObject report = material.getExtractionReportJson() == null ? null : JSONUtil.parseObj(material.getExtractionReportJson());
        if (report != null) report.remove("pageTexts");
        result.put("extractionReport", report);
        result.put("recordId", material.getRecordId()); result.put("questionId", material.getQuestionId()); result.put("createdAt", material.getCreatedAt()); return result;
    }
}
