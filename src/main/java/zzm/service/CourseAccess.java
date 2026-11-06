package zzm.service;

import zzm.entity.AccountUser;
import zzm.entity.Course;
import zzm.entity.CourseMember;
import zzm.mapper.CourseMapper;
import zzm.mapper.CourseMemberMapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import static zzm.exception.ApiErrors.error;

/** 课程和材料共用访问校验，避免业务服务之间相互依赖。 */
@Component
@RequiredArgsConstructor
public class CourseAccess {
    private final CourseMapper courses;
    private final CourseMemberMapper members;
    private final AccountService accounts;

    public Course requireAccess(String id, AccountUser user, boolean teacher) {
        if (Boolean.TRUE.equals(user.getMustChangePassword())) throw error(403, "Password change required");
        if (teacher) accounts.requireStaff(user);
        Course course = courses.selectById(id);
        if (course == null) throw error(404, "Course not found");
        CourseMember membership = members.selectOne(Wrappers.<CourseMember>lambdaQuery().eq(CourseMember::getCourseId, id)
            .eq(CourseMember::getUserId, user.getId()).eq(CourseMember::getArchived, false));
        if (membership == null || teacher && !"teacher".equals(membership.getRole())) throw error(403, "Course access denied");
        if (!teacher && Boolean.TRUE.equals(course.getArchived())) throw error(404, "Course is archived");
        return course;
    }
}
