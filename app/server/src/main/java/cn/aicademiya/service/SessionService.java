package cn.aicademiya.service;

import cn.aicademiya.dto.*;
import cn.aicademiya.entity.*;
import com.baomidou.mybatisplus.extension.service.IService;
import java.util.*;

public interface SessionService extends IService<TeachingSession> {
    TeachingSession require(String id, AccountUser user, boolean teacher);
    List<Map<String, Object>> listCourse(String courseId, AccountUser user);
    TeachingSession create(String courseId, Requests.SessionInput input, AccountUser user);
    TeachingSession edit(String id, Requests.SessionInput input, AccountUser user);
    Map<String, Object> view(TeachingSession session, boolean teacher);
    Map<String, Object> published(String id, String versionId, AccountUser user);
    SessionVersion version(String sessionId, String versionId);
    SessionVersion publish(String id, long revision, AccountUser user);
    void restore(String id, String versionId, long revision, AccountUser user);
    void archive(String id, boolean archived, AccountUser user);
    List<Map<String, Object>> versions(String id, AccountUser user);
    TaskContent validateContent(TaskContent content, List<String> materialIds, boolean publishing);
    Map<String, Object> studentProjection(Map<String, Object> snapshot);
}
