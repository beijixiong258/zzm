package cn.aicademiya.service;

import cn.aicademiya.dto.Requests;
import cn.aicademiya.entity.*;
import com.baomidou.mybatisplus.spring.service.IService;
import java.util.Map;

public interface GenerationService extends IService<GenerationJob> {
    void recoverProcessing();
    void processNext();
    java.util.List<Map<String, Object>> listJobs(String sessionId, AccountUser user);
    Map<String, Object> assistTeacher(Requests.Chat input, AccountUser user);
    GenerationJob start(String sessionId, Requests.Generation input, AccountUser user);
    GenerationJob require(String id, AccountUser user);
    TeachingSession apply(String id, AccountUser user);
    Map<String, Object> view(GenerationJob job);
}
