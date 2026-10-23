package cn.aicademiya.service;

import cn.aicademiya.dto.Requests;
import cn.aicademiya.entity.*;
import com.baomidou.mybatisplus.spring.service.IService;
import java.util.*;

public interface LearningService extends IService<LearningRecord> {
    Map<String, Object> previewWorkspace(String id, AccountUser user);
    LearningRecord startPreview(String id, AccountUser user);
    List<Map<String,Object>> attachments(String id, AccountUser user);
    Map<String,Object> uploadAttachment(String id, String questionId, org.springframework.web.multipart.MultipartFile file, AccountUser user);
    Map<String,Object> removeAttachment(String id, String attachmentId, long revision, AccountUser user);
    Map<String,Object> approveFeedback(String id, String requestId, String text, AccountUser user);
    Map<String, Object> workspace(String sessionId, String versionId, AccountUser user);
    LearningRecord start(String sessionId, String versionId, AccountUser user);
    Map<String, Object> saveAnswers(String id, Requests.Answer input, AccountUser user);
    Map<String, Object> resetConversation(String id, long revision, AccountUser user);
    Map<String, Object> context(String id, Requests.Chat input, AccountUser user);
    Map<String, Object> chat(String id, Requests.Chat input, AccountUser user);
    Map<String, Object> submit(String id, long revision, AccountUser user);
    List<Map<String, Object>> roster(String sessionId, String versionId, AccountUser user);
    Map<String, Object> observe(String id, AccountUser user);
    Map<String, Object> review(String id, Requests.Review input, AccountUser user);
    List<Map<String, Object>> history(AccountUser user);
    Map<String, Object> recordHistory(String id, String kind, int page, int size, Long revision, AccountUser user);
    Map<String, Object> historyMessages(String id, String historyId, int page, int size, Long revision, AccountUser user);
    Map<String, Object> view(LearningRecord record);
    byte[] exportResult(String id, AccountUser user, String materialBaseUrl);
}
