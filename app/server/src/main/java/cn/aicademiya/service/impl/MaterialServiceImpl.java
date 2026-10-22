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
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
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
    private final SessionVersionMapper versions;
    private final TeachingSessionMapper sessions;
    private final LearningRecordMapper records;
    @Override public List<Map<String, Object>> library(String courseId, AccountUser user) {
        courses.requireAccess(courseId, user, true);
        return lambdaQuery().eq(CourseMaterial::getCourseId, courseId).orderByAsc(CourseMaterial::getRelativePath).list().stream().map(this::view).toList();
    }
    @Override public CourseMaterial upload(String courseId, MultipartFile file, String relativePath, String visibility, AccountUser user) {
        courses.requireAccess(courseId, user, true);
        if (!Set.of("student", "teacher").contains(visibility) || file.isEmpty() || file.getSize() > 25L * 1024 * 1024) throw error(422, "Invalid file or visibility");
        String name = Objects.requireNonNullElse(file.getOriginalFilename(), "material").replace('\\', '/');
        name = name.substring(name.lastIndexOf('/') + 1);
        if (name.isBlank() || name.length() > 255) throw error(422, "Invalid file name");
        String extension = name.contains(".") ? name.substring(name.lastIndexOf('.')).toLowerCase(Locale.ROOT) : "";
        if (!Set.of(".pdf", ".docx", ".doc", ".pptx", ".txt", ".md", ".xlsx", ".png", ".jpg", ".jpeg", ".webp", ".ppt", ".xls").contains(extension)) throw error(422, "Unsupported file type");
        String sourcePath = relativePath == null || relativePath.isBlank() ? name : relativePath.replace('\\', '/');
        if (sourcePath.length() > 1024 || sourcePath.startsWith("/") || sourcePath.contains(":") || Arrays.asList(sourcePath.split("/")).contains("..")) throw error(422, "Invalid folder path");
        CourseMaterial material = new CourseMaterial(); material.setId(IdUtil.fastSimpleUUID());
        Path destination = Path.of(properties.getUploadDir()).toAbsolutePath().normalize().resolve(material.getId() + extension);
        try { Files.createDirectories(destination.getParent()); file.transferTo(destination); }
        catch (IOException exception) { throw error(500, "File could not be saved"); }
        material.setCourseId(courseId); material.setTitle(name); material.setFileName(name); material.setRelativePath(sourcePath);
        material.setMimeType(switch (extension) { case ".pdf" -> "application/pdf"; case ".docx" -> "application/vnd.openxmlformats-officedocument.wordprocessingml.document"; case ".doc" -> "application/msword"; case ".pptx" -> "application/vnd.openxmlformats-officedocument.presentationml.presentation"; case ".ppt" -> "application/vnd.ms-powerpoint"; case ".xlsx" -> "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"; case ".xls" -> "application/vnd.ms-excel"; case ".txt", ".md" -> "text/plain"; case ".png" -> "image/png"; case ".jpg", ".jpeg" -> "image/jpeg"; case ".webp" -> "image/webp"; default -> "application/octet-stream"; });
        material.setStoragePath(destination.toString()); material.setVisibility(visibility); material.setStatus("queued");
        material.setTextContent(""); material.setErrorMessage(""); material.setArchived(false); material.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC));
        save(material); return material;
    }
    @Override public CourseMaterial requireFile(String id, String versionId, AccountUser user) {
        CourseMaterial material = getById(id);
        if (material == null) throw error(404, "Material not found");
        courses.requireAccess(material.getCourseId(), user, !"student".equals(user.getRole()));
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
        CourseMaterial material = requireFile(id, null, user); courses.requireAccess(material.getCourseId(), user, true);
        if ("processing".equals(material.getStatus())) throw error(409, "Material is processing");
        if (!lambdaUpdate().eq(CourseMaterial::getId, id).ne(CourseMaterial::getStatus, "processing")
            .set(CourseMaterial::getStatus, "queued").set(CourseMaterial::getErrorMessage, "")
            .set(CourseMaterial::getExtractionReportJson, null).set(CourseMaterial::getTextContent, "").update()) throw error(409, "Material is processing");
    }
    @Override public void recoverProcessing() {
        lambdaUpdate().eq(CourseMaterial::getStatus, "processing")
            .set(CourseMaterial::getStatus, "queued").set(CourseMaterial::getExtractionReportJson, null)
            .set(CourseMaterial::getTextContent, "")
            .set(CourseMaterial::getErrorMessage, "Document processing was interrupted and has been queued again.").update();
    }

    @Override public void processNext() {
        List<CourseMaterial> queued = lambdaQuery().eq(CourseMaterial::getStatus, "queued")
            .eq(CourseMaterial::getArchived, false).orderByAsc(CourseMaterial::getCreatedAt)
            .page(new Page<CourseMaterial>(1, 1, false)).getRecords();
        if (queued.isEmpty()) return;
        CourseMaterial material = queued.getFirst();
        if (!lambdaUpdate().eq(CourseMaterial::getId, material.getId()).eq(CourseMaterial::getStatus, "queued")
            .eq(CourseMaterial::getArchived, false).set(CourseMaterial::getStatus, "processing")
            .set(CourseMaterial::getTextContent, "").set(CourseMaterial::getErrorMessage, "")
            .set(CourseMaterial::getExtractionReportJson, JSONUtil.toJsonStr(new DocumentExtraction.Report())).update()) return;
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

    @Override public void requireProcessed(List<CourseMaterial> selected) {
        for (CourseMaterial material : selected) {
            if (!Set.of("ready", "needsReview").contains(material.getStatus())
                || material.getTextContent() == null || material.getTextContent().isBlank()) {
                throw error(422, "Select processed materials with readable content");
            }
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
        List<CourseMaterial> result = lambdaQuery().eq(CourseMaterial::getCourseId, courseId).in(CourseMaterial::getId, ids).eq(CourseMaterial::getArchived, false).list();
        if (result.size() != new HashSet<>(ids).size()) throw error(422, "Selected materials must belong to this course and be active");
        return result;
    }
    @Override public Map<String, Object> view(CourseMaterial material) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", material.getId()); result.put("title", material.getTitle()); result.put("fileName", material.getFileName());
        result.put("relativePath", material.getRelativePath()); result.put("mimeType", material.getMimeType()); result.put("status", material.getStatus());
        result.put("visibility", material.getVisibility()); result.put("errorMessage", material.getErrorMessage()); result.put("archived", material.getArchived());
        result.put("extractionReport", material.getExtractionReportJson() == null ? null : JSONUtil.parseObj(material.getExtractionReportJson()));
        result.put("createdAt", material.getCreatedAt()); return result;
    }
}
