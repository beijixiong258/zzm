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
        return lambdaQuery().eq(Course::getWorkspace, false).in(Course::getId, ids).eq("student".equals(user.getRole()), Course::getArchived, false)
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
    @Override public Map<String, Object> view(Course course, AccountUser user) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", course.getId()); result.put("code", course.getCode()); result.put("title", course.getTitle());
        result.put("description", course.getDescription()); result.put("archived", course.getArchived());
        result.put("workspace", Boolean.TRUE.equals(course.getWorkspace()));
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
    @Override @Transactional public void addMember(String id, Requests.Account input, AccountUser user) {
        addMembers(id, List.of(input), user);
    }
    @Override @Transactional public void addMembers(String id, List<Requests.Account> input, AccountUser user) {
        requireAccess(id, user, true);
        List<String> emails = input.stream().map(a -> a.getEmail().trim().toLowerCase(Locale.ROOT)).toList();
        if (new HashSet<>(emails).size() != emails.size()) throw error(422, "The member list contains duplicate email addresses");
        Map<String, AccountUser> known = new HashMap<>();
        accounts.lambdaQuery().in(AccountUser::getEmail, emails).list().forEach(a -> known.put(a.getEmail(), a));
        List<Requests.Account> create = new ArrayList<>();
        for (Requests.Account account : input) {
            AccountUser person = known.get(account.getEmail().trim().toLowerCase(Locale.ROOT));
            if (person == null) {
                if (!"student".equals(account.getRole())) throw error(422, "Create teacher accounts in account management first");
                create.add(account);
            } else {
                if (Boolean.TRUE.equals(person.getArchived())) throw error(422, "Account is archived");
                if ("student".equals(account.getRole()) != "student".equals(person.getRole())) throw error(422, "The account role does not match the requested course membership");
            }
        }
        List<AccountUser> created = create.isEmpty() ? List.of() : accounts.createMany(create, "student");
        if (!created.isEmpty()) accounts.lambdaUpdate().in(AccountUser::getId, created.stream().map(AccountUser::getId).toList()).set(AccountUser::getMustChangePassword, true).update();
        created.forEach(a -> known.put(a.getEmail(), a));
        Set<String> existingIds = new HashSet<>();
        members.selectList(Wrappers.<CourseMember>lambdaQuery().eq(CourseMember::getCourseId, id)).forEach(m -> existingIds.add(m.getUserId()));
        List<CourseMember> additions = new ArrayList<>();
        for (AccountUser person : known.values()) {
            if (existingIds.contains(person.getId())) continue;
            CourseMember member = new CourseMember(); member.setCourseId(id); member.setUserId(person.getId());
            member.setRole("student".equals(person.getRole()) ? "student" : "teacher"); member.setArchived(false); additions.add(member);
        }
        if (!additions.isEmpty()) members.insert(additions);
        members.update(Wrappers.<CourseMember>lambdaUpdate().eq(CourseMember::getCourseId, id)
            .in(CourseMember::getUserId, known.values().stream().map(AccountUser::getId).toList()).set(CourseMember::getArchived, false));
    }
    @Override public void archiveMember(String id, String userId, boolean archived, AccountUser user) {
        Course course = requireAccess(id, user, true);
        if (archived && course.getOwnerId().equals(userId)) throw error(422, "The course owner must remain a member");
        members.update(Wrappers.<CourseMember>lambdaUpdate().eq(CourseMember::getCourseId, id).eq(CourseMember::getUserId, userId).set(CourseMember::getArchived, archived));
    }
    @Override @Transactional public Map<String, Object> inviteStudent(String courseId, Requests.StudentInvitation input, AccountUser user) {
        requireAccess(courseId, user, true);
        Map<String, Object> result = accounts.createInvitedStudent(input);
        CourseMember member = new CourseMember(); member.setCourseId(courseId); member.setUserId(result.get("id").toString());
        member.setRole("student"); member.setArchived(false); members.insert(member); return result;
    }
    @Override @Transactional public Map<String, Object> changeInvitation(String courseId, String studentId, boolean enabled, AccountUser user) {
        requireAccess(courseId, user, true);
        if (members.selectCount(Wrappers.<CourseMember>lambdaQuery().eq(CourseMember::getCourseId, courseId)
            .eq(CourseMember::getUserId, studentId).eq(CourseMember::getRole, "student").eq(CourseMember::getArchived, false)) == 0)
            throw error(404, "Student is not an active member of this course");
        return accounts.invitation(studentId, enabled);
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
