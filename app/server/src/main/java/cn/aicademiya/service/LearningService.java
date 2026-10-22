package cn.aicademiya.service;

import cn.aicademiya.dto.Requests;
import cn.aicademiya.entity.*;
import com.baomidou.mybatisplus.extension.service.IService;
import java.util.*;

public interface LearningService extends IService<LearningRecord> {
    Map<String, Object> workspace(String sessionId, String versionId, AccountUser user);
    LearningRecord start(String sessionId, String versionId, AccountUser user);
    Map<String, Object> saveAnswers(String id, Requests.Answer input, AccountUser user);
    Map<String, Object> chat(String id, Requests.Chat input, AccountUser user);
    Map<String, Object> submit(String id, long revision, AccountUser user);
    List<Map<String, Object>> roster(String sessionId, String versionId, AccountUser user);
    Map<String, Object> observe(String id, AccountUser user);
    Map<String, Object> review(String id, Requests.Review input, AccountUser user);
    List<Map<String, Object>> history(AccountUser user);
    Map<String, Object> view(LearningRecord record);
}
