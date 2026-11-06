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
import static zzm.exception.ApiErrors.error;

@Service
@RequiredArgsConstructor
public class CourseServiceImpl extends ServiceImpl<CourseMapper, Course> implements CourseService {
    private final CourseMemberMapper members;
    private final AccountService accounts;
    private final CourseAccess courseAccess;
    private final TeachingSessionMapper tasks;
    private final GenerationJobMapper jobs;
    private final MaterialService materials;
    private final LearningRecordMapper records;
    @Override public Course requireAccess(String id, AccountUser user, boolean teacher) {
        return courseAccess.requireAccess(id, user, teacher);
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
        Course course = lockCourse(id);
        if (!course.getOwnerId().equals(user.getId())) throw error(403, "Only the course owner can delete this course.");
        if (Boolean.TRUE.equals(course.getWorkspace())) throw error(409, "The teaching workspace cannot be deleted.");
        List<String> taskIds = tasks.selectList(Wrappers.<TeachingSession>lambdaQuery()
            .eq(TeachingSession::getCourseId, id).orderByAsc(TeachingSession::getId).last("FOR UPDATE"))
            .stream().map(TeachingSession::getId).toList();
        if (!taskIds.isEmpty() && !jobs.selectList(Wrappers.<GenerationJob>lambdaQuery().in(GenerationJob::getSessionId, taskIds)
            .in(GenerationJob::getStatus, "queued", "running").last("FOR UPDATE")).isEmpty())
            throw error(409, "Wait for course generation to finish before deleting the course.");
        materials.removeCourseMaterials(id, user);
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
        addStudentMembership(id, student.getId(), true);
    }
    private void addStudentMembership(String courseId, String studentId, boolean allowRestore) {
        // 同一课程的成员写入串行，重复添加或同时入课均读取最新成员状态。
        Course course = lockCourse(courseId);
        if (!allowRestore && (Boolean.TRUE.equals(course.getArchived()) || Boolean.TRUE.equals(course.getWorkspace())))
            throw error(404, "Course join code is invalid");
        CourseMember member = members.selectOne(Wrappers.<CourseMember>lambdaQuery()
            .eq(CourseMember::getCourseId, courseId).eq(CourseMember::getUserId, studentId).last("FOR UPDATE"));
        if (member == null) {
            member = new CourseMember(); member.setCourseId(courseId); member.setUserId(studentId);
            member.setRole("student"); member.setArchived(false); members.insert(member);
        } else if (Boolean.TRUE.equals(member.getArchived())) {
            if (!allowRestore) throw error(403, "Ask your teacher to restore your course membership");
            // 教师重新添加时恢复入课资格，已删除的学习记录不会恢复。
            members.update(Wrappers.<CourseMember>lambdaUpdate().eq(CourseMember::getId, member.getId())
                .set(CourseMember::getRole, "student").set(CourseMember::getArchived, false));
        }
    }
    @Override @Transactional public void removeStudent(String id, String studentId, AccountUser user) {
        requireAccess(id, user, true);
        lockCourse(id);
        CourseMember member = members.selectOne(Wrappers.<CourseMember>lambdaQuery()
            .eq(CourseMember::getCourseId, id).eq(CourseMember::getUserId, studentId).last("FOR UPDATE"));
        if (member == null) throw error(404, "Course member not found");
        if (!"student".equals(member.getRole())) throw error(403, "Only students can be removed from a course.");
        deleteStudentRecords(id, studentId, user);
        members.update(Wrappers.<CourseMember>lambdaUpdate().eq(CourseMember::getId, member.getId())
            .set(CourseMember::getArchived, true));
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
        materials.removeTaskAttachments(recordIds, user);
        // 作答、对话和辅导状态随主记录删除，历史表由外键级联删除；附件进入现有回收流程。
        records.delete(Wrappers.<LearningRecord>lambdaQuery().in(LearningRecord::getId, recordIds));
    }
    @Override @Transactional public void join(String code, AccountUser user) {
        if (!"student".equals(user.getRole()) || Boolean.TRUE.equals(user.getMustChangePassword())) throw error(403, "Student access required");
        Course course = lambdaQuery().eq(Course::getJoinCode, code.trim()).eq(Course::getArchived, false).one();
        if (course == null || Boolean.TRUE.equals(course.getWorkspace())) throw error(404, "Course join code is invalid");
        addStudentMembership(course.getId(), user.getId(), false);
    }
    private Course lockCourse(String id) {
        Course course = lambdaQuery().eq(Course::getId, id).last("FOR UPDATE").one();
        if (course == null) throw error(404, "Course not found");
        return course;
    }
}
