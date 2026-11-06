package zzm.service;

import zzm.dto.Requests;
import zzm.entity.*;
import com.baomidou.mybatisplus.spring.service.IService;
import java.util.List;
import java.util.Map;

public interface CourseService extends IService<Course> {
    Course requireAccess(String id, AccountUser user, boolean teacher);
    List<Map<String, Object>> mine(AccountUser user);
    Course workbench(AccountUser user);
    Course create(Requests.CourseInput input, AccountUser user);
    Course edit(String id, Requests.CourseInput input, AccountUser user);
    void archive(String id, boolean archived, AccountUser user);
    void deleteCourse(String id, AccountUser user);
    Map<String, Object> view(Course course, AccountUser user);
    List<Map<String, Object>> members(String id, AccountUser user);
    List<AccountUser> students(String courseId);
    void addStudent(String id, Requests.CourseStudent input, AccountUser user);
    void archiveMember(String id, String userId, boolean archived, AccountUser user);
    void join(String code, AccountUser user);
}
