package zzm.service.impl;

import zzm.dto.Requests;
import zzm.entity.*;
import zzm.mapper.*;
import zzm.service.*;
import cn.hutool.core.util.IdUtil;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.*;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import static zzm.exception.ApiErrors.error;

@Service
@RequiredArgsConstructor
public class CourseServiceImpl extends ServiceImpl<CourseMapper, Course> implements CourseService {
    private final CourseMemberMapper members;
    private final AccountService accounts;
    private final TeachingSessionMapper tasks;
    private final GenerationJobMapper jobs;
    private final CourseMaterialMapper materials;
    private final LearningRecordMapper records;
    @Override public Course requireAccess(String id, AccountUser user, boolean teacher) {
        if (Boolean.TRUE.equals(user.getMustChangePassword())) throw error(403, "Password change required");
        if (teacher) accounts.requireStaff(user);
        Course course = getById(id);
        if (course == null) throw error(404, "Course not found");
        CourseMember membership = members.selectOne(Wrappers.<CourseMember>lambdaQuery().eq(CourseMember::getCourseId, id)
            .eq(CourseMember::getUserId, user.getId()).eq(CourseMember::getArchived, false));
        if (membership == null || teacher && !"teacher".equals(membership.getRole())) throw error(403, "Course access denied");
        if (!teacher && Boolean.TRUE.equals(course.getArchived())) throw error(404, "Course is archived");
        return course;
    }
    @Override public List<Map<String, Object>> mine(AccountUser user) {
        List<String> ids = members.selectList(Wrappers.<CourseMember>lambdaQuery().eq(CourseMember::getUserId, user.getId())
            .eq(CourseMember::getArchived, false)).stream().map(CourseMember::getCourseId).toList();
        if (ids.isEmpty()) return List.of();
        return lambdaQuery().in(Course::getId, ids).eq("student".equals(user.getRole()), Course::getArchived, false)
            .orderByAsc(Course::getTitle).list().stream().map(c -> view(c, user)).toList();
    }
    @Override @Transactional public Course create(Requests.CourseInput input, AccountUser user) {
        accounts.requireStaff(user);
        Course course = new Course(); fill(course, input); course.setOwnerId(user.getId());
        course.setJoinCode(IdUtil.fastSimpleUUID().substring(0, 12)); course.setArchived(false); course.setWorkspace(false); save(course);
        CourseMember member = new CourseMember(); member.setCourseId(course.getId()); member.setUserId(user.getId());
        member.setRole("teacher"); member.setArchived(false); members.insert(member); return course;
    }
    @Override @Transactional public synchronized Course workbench(AccountUser user) {
        accounts.requireStaff(user);
        Course existing = lambdaQuery().eq(Course::getOwnerId, user.getId()).eq(Course::getWorkspace, true).last("LIMIT 1").one();
        if (existing != null) return existing;
        Requests.CourseInput input = new Requests.CourseInput(); input.setTitle("Teacher workbench"); input.setCode("WORKBENCH");
        Course course = create(input, user); course.setWorkspace(true); updateById(course); return course;
    }
    @Override public Course edit(String id, Requests.CourseInput input, AccountUser user) {
        Course course = requireAccess(id, user, true); fill(course, input); updateById(course); return course;
    }
    private void fill(Course course, Requests.CourseInput input) {
        course.setTitle(input.getTitle().trim()); course.setCode(input.getCode().trim());
        course.setDescription(input.getDescription()); course.setSystemInstructions(input.getSystemInstructions()); course.setCourseInformation(input.getCourseInformation()); course.setStudentProfile(input.getStudentProfile());
    }
    @Override public void archive(String id, boolean archived, AccountUser user) {
        requireAccess(id, user, true); lambdaUpdate().eq(Course::getId, id).set(Course::getArchived, archived).update();
    }
    @Override @Transactional public void deleteCourse(String id, AccountUser user) {
        requireAccess(id, user, true);
        Course course = lambdaQuery().eq(Course::getId, id).last("FOR UPDATE").one();
        if (course == null) throw error(404, "Course not found");
        if (!course.getOwnerId().equals(user.getId())) throw error(403, "Only the course owner can delete this course.");
        if (Boolean.TRUE.equals(course.getWorkspace())) throw error(409, "The teaching workspace cannot be deleted.");
        List<String> taskIds = tasks.selectList(Wrappers.<TeachingSession>lambdaQuery()
            .eq(TeachingSession::getCourseId, id).orderByAsc(TeachingSession::getId).last("FOR UPDATE"))
            .stream().map(TeachingSession::getId).toList();
        if (!taskIds.isEmpty() && !jobs.selectList(Wrappers.<GenerationJob>lambdaQuery().in(GenerationJob::getSessionId, taskIds)
            .in(GenerationJob::getStatus, "queued", "running").last("FOR UPDATE")).isEmpty())
            throw error(409, "Wait for course generation to finish before deleting the course.");
        List<CourseMaterial> files = materials.selectList(Wrappers.<CourseMaterial>lambdaQuery()
            .eq(CourseMaterial::getCourseId, id).orderByAsc(CourseMaterial::getId).last("FOR UPDATE"));
        if (files.stream().anyMatch(file -> "processing".equals(file.getStatus())))
            throw error(409, "Wait for course materials to finish processing before deleting the course.");
        materials.update(Wrappers.<CourseMaterial>lambdaUpdate().eq(CourseMaterial::getCourseId, id)
            .isNull(CourseMaterial::getFileRemovedAt).set(CourseMaterial::getFileRemovedAt, LocalDateTime.now(ZoneOffset.UTC))
            .set(CourseMaterial::getRemovedBy, user.getId()));
        materials.update(Wrappers.<CourseMaterial>lambdaUpdate().eq(CourseMaterial::getCourseId, id)
            .set(CourseMaterial::getArchived, true).set(CourseMaterial::getStatus, "taskDeleted")
            .set(CourseMaterial::getTextContent, "").set(CourseMaterial::getExtractionReportJson, null).set(CourseMaterial::getErrorMessage, ""));
        // 任务、版本、学习记录和成员由外键级联删除，材料暂存于原有文件回收队列。
        if (baseMapper.deleteById(id) != 1) throw error(409, "Course changed. Reload before deleting.");
    }
    @Override public Map<String, Object> view(Course course, AccountUser user) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", course.getId()); result.put("code", course.getCode()); result.put("title", course.getTitle());
        result.put("description", course.getDescription()); result.put("archived", course.getArchived());
        result.put("workspace", Boolean.TRUE.equals(course.getWorkspace()));
        result.put("canDelete", !Boolean.TRUE.equals(course.getWorkspace()) && course.getOwnerId().equals(user.getId()));
        if (!"student".equals(user.getRole())) {
            result.put("courseInformation", Objects.toString(course.getCourseInformation(), "")); result.put("studentProfile", Objects.toString(course.getStudentProfile(), "")); result.put("systemInstructions", course.getSystemInstructions()); result.put("joinCode", course.getJoinCode());
        }
        return result;
    }
    @Override public List<Map<String, Object>> members(String id, AccountUser user) {
        requireAccess(id, user, true);
        List<CourseMember> rows = members.selectList(Wrappers.<CourseMember>lambdaQuery().eq(CourseMember::getCourseId, id));
        if (rows.isEmpty()) return List.of();
        Map<String, AccountUser> people = new HashMap<>();
        accounts.listByIds(rows.stream().map(CourseMember::getUserId).toList()).forEach(a -> people.put(a.getId(), a));
        return rows.stream().filter(m -> people.containsKey(m.getUserId())).map(m -> {
            Map<String, Object> result = new LinkedHashMap<>(accounts.publicUser(people.get(m.getUserId())));
            result.put("membershipRole", m.getRole()); result.put("membershipArchived", m.getArchived()); return result;
        }).toList();
    }
    @Override public List<AccountUser> students(String courseId) {
        List<String> ids = members.selectList(Wrappers.<CourseMember>lambdaQuery().eq(CourseMember::getCourseId, courseId)
            .eq(CourseMember::getRole, "student").eq(CourseMember::getArchived, false)).stream().map(CourseMember::getUserId).toList();
        return ids.isEmpty() ? List.of() : accounts.lambdaQuery().in(AccountUser::getId, ids).eq(AccountUser::getArchived, false).orderByAsc(AccountUser::getName).list();
    }
    @Override @Transactional public void addStudent(String id, Requests.CourseStudent input, AccountUser user) {
        requireAccess(id, user, true);
        String account = input.getAccount().trim().toLowerCase(Locale.ROOT);
        boolean email = account.contains("@");
        AccountUser student = accounts.lambdaQuery().eq(email, AccountUser::getEmail, account)
            .eq(!email, AccountUser::getUsername, account).one();
        if (student == null) throw error(404, "Student account not found. Check the username or email address.");
        if (!"student".equals(student.getRole())) throw error(422, "This account is not a student account.");
        if (Boolean.TRUE.equals(student.getArchived())) throw error(422, "Account is archived");
        CourseMember member = members.selectOne(Wrappers.<CourseMember>lambdaQuery()
            .eq(CourseMember::getCourseId, id).eq(CourseMember::getUserId, student.getId()));
        if (member == null) {
            member = new CourseMember(); member.setCourseId(id); member.setUserId(student.getId());
            member.setRole("student"); member.setArchived(false); members.insert(member);
        } else {
            // 教师重新添加时恢复入课资格，已删除的学习记录不会恢复。
            members.update(Wrappers.<CourseMember>lambdaUpdate().eq(CourseMember::getId, member.getId())
                .set(CourseMember::getRole, "student").set(CourseMember::getArchived, false));
        }
    }
    @Override @Transactional public void archiveMember(String id, String userId, boolean archived, AccountUser user) {
        requireAccess(id, user, true);
        CourseMember member = members.selectOne(Wrappers.<CourseMember>lambdaQuery()
            .eq(CourseMember::getCourseId, id).eq(CourseMember::getUserId, userId));
        if (member == null) throw error(404, "Course member not found");
        if (!"student".equals(member.getRole())) throw error(403, "Only student memberships can be changed here.");
        if (archived) deleteStudentRecords(id, userId, user);
        members.update(Wrappers.<CourseMember>lambdaUpdate().eq(CourseMember::getId, member.getId())
            .set(CourseMember::getArchived, archived));
    }
    private void deleteStudentRecords(String courseId, String studentId, AccountUser user) {
        // 与开始任务共用任务行锁，防止移出课程时并发创建新的学习记录。
        List<String> taskIds = tasks.selectList(Wrappers.<TeachingSession>lambdaQuery()
            .eq(TeachingSession::getCourseId, courseId).orderByAsc(TeachingSession::getId).last("FOR UPDATE"))
            .stream().map(TeachingSession::getId).toList();
        if (taskIds.isEmpty()) return;
        List<String> recordIds = records.selectList(Wrappers.<LearningRecord>lambdaQuery()
            .select(LearningRecord::getId).in(LearningRecord::getSessionId, taskIds).eq(LearningRecord::getUserId, studentId)
            .orderByAsc(LearningRecord::getId).last("FOR UPDATE"))
            .stream().map(LearningRecord::getId).toList();
        if (recordIds.isEmpty()) return;
        List<CourseMaterial> attachments = materials.selectList(Wrappers.<CourseMaterial>lambdaQuery()
            .select(CourseMaterial::getId, CourseMaterial::getStatus).in(CourseMaterial::getRecordId, recordIds)
            .orderByAsc(CourseMaterial::getId).last("FOR UPDATE"));
        if (attachments.stream().anyMatch(file -> "processing".equals(file.getStatus())))
            throw error(409, "Wait for the student's attachments to finish processing before removing them from the course.");
        materials.update(Wrappers.<CourseMaterial>lambdaUpdate().in(CourseMaterial::getRecordId, recordIds)
            .isNull(CourseMaterial::getFileRemovedAt).set(CourseMaterial::getFileRemovedAt, LocalDateTime.now(ZoneOffset.UTC))
            .set(CourseMaterial::getRemovedBy, user.getId()));
        materials.update(Wrappers.<CourseMaterial>lambdaUpdate().in(CourseMaterial::getRecordId, recordIds)
            .set(CourseMaterial::getArchived, true).set(CourseMaterial::getStatus, "taskDeleted")
            .set(CourseMaterial::getTextContent, "").set(CourseMaterial::getExtractionReportJson, null).set(CourseMaterial::getErrorMessage, ""));
        // 作答、对话和辅导状态随主记录删除，历史表由外键级联删除；附件进入现有回收流程。
        records.delete(Wrappers.<LearningRecord>lambdaQuery().in(LearningRecord::getId, recordIds));
    }
    @Override @Transactional public void join(String code, AccountUser user) {
        if (!"student".equals(user.getRole()) || Boolean.TRUE.equals(user.getMustChangePassword())) throw error(403, "Student access required");
        Course course = lambdaQuery().eq(Course::getJoinCode, code.trim()).eq(Course::getArchived, false).one();
        if (course == null || Boolean.TRUE.equals(course.getWorkspace())) throw error(404, "Course join code is invalid");
        CourseMember member = members.selectOne(Wrappers.<CourseMember>lambdaQuery().eq(CourseMember::getCourseId, course.getId()).eq(CourseMember::getUserId, user.getId()));
        if (member != null) {
            if (Boolean.TRUE.equals(member.getArchived())) throw error(403, "Ask your teacher to restore your course membership");
            return;
        }
        member = new CourseMember(); member.setCourseId(course.getId()); member.setUserId(user.getId()); member.setRole("student"); member.setArchived(false); members.insert(member);
    }
}
