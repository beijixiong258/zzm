package cn.aicademiya.service.impl;

import cn.aicademiya.config.AppProperties;
import cn.aicademiya.entity.*;
import cn.aicademiya.mapper.*;
import cn.aicademiya.service.LegacyImportService;
import cn.hutool.json.*;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
public class LegacyImportServiceImpl extends ServiceImpl<LegacyRecordMapper, LegacyRecord> implements LegacyImportService, ApplicationRunner {
    private final AccountUserMapper users;
    private final CourseMapper courses;
    private final CourseMemberMapper members;
    private final TeachingSessionMapper sessions;
    private final SessionVersionMapper versions;
    private final CourseMaterialMapper materials;
    private final LearningRecordMapper records;
    private final AppProperties properties;
    @Value("${app.legacy-import:}") private String importDirectory;

    @Override @Transactional(rollbackFor = Exception.class)
    public void run(ApplicationArguments arguments) throws Exception {
        if (importDirectory.isBlank()) return;
        if (users.selectCount(null) != 0 || courses.selectCount(null) != 0 || count() != 0) throw new IllegalStateException("Legacy import requires an empty MySQL application database; no data was overwritten");
        Path directory = Path.of(importDirectory).toAbsolutePath().normalize();
        JSONObject manifest = JSONUtil.parseObj(Files.readString(directory.resolve("manifest.json"), StandardCharsets.UTF_8));
        List<AccountUser> importedUsers = manifest.getJSONArray("users").toList(AccountUser.class);
        List<CourseMaterial> importedMaterials = manifest.getJSONArray("materials").toList(CourseMaterial.class);
        Path upload = Path.of(properties.getUploadDir()).toAbsolutePath().normalize(); Files.createDirectories(upload);
        for (CourseMaterial material : importedMaterials) {
            String filename = material.getStoragePath(); Path source = directory.resolve("files").resolve(filename).normalize();
            Path target = upload.resolve(filename).normalize();
            if (!source.startsWith(directory.resolve("files")) || !target.startsWith(upload) || !target.getFileName().toString().equals(filename)) throw new IllegalArgumentException("Invalid migration file path");
            if (Files.isRegularFile(source)) {
                if (Files.exists(target)) throw new IllegalStateException("Migration refuses to overwrite an existing uploaded file: " + filename);
                Files.copy(source, target);
            } else {
                material.setErrorMessage("The original file was unavailable during migration; extracted text is retained");
            }
            material.setStoragePath(target.toString());
        }
        if (!importedUsers.isEmpty()) users.insert(importedUsers);
        List<Course> importedCourses = manifest.getJSONArray("courses").toList(Course.class);
        if (!importedCourses.isEmpty()) courses.insert(importedCourses);
        List<CourseMember> importedMembers = manifest.getJSONArray("members").toList(CourseMember.class);
        if (!importedMembers.isEmpty()) members.insert(importedMembers);
        List<TeachingSession> importedSessions = manifest.getJSONArray("sessions").toList(TeachingSession.class);
        if (!importedSessions.isEmpty()) sessions.insert(importedSessions);
        if (!importedMaterials.isEmpty()) materials.insert(importedMaterials);
        List<SessionVersion> importedVersions = manifest.getJSONArray("versions").toList(SessionVersion.class);
        if (!importedVersions.isEmpty()) versions.insert(importedVersions);
        List<LearningRecord> importedRecords = manifest.getJSONArray("records").toList(LearningRecord.class);
        if (!importedRecords.isEmpty()) records.insert(importedRecords);
        saveBatch(manifest.getJSONArray("legacy").toList(LegacyRecord.class));
        log.info("Legacy import completed: {} accounts, {} courses, {} tasks, {} learning records", importedUsers.size(), importedCourses.size(), importedSessions.size(), importedRecords.size());
    }
}
