package zzm.service;

import com.baomidou.mybatisplus.spring.service.IService;
import zzm.dto.TaskContent;
import zzm.entity.CourseMaterial;
import zzm.entity.LearningAssessment;
import zzm.entity.LearningRecord;
import java.math.BigDecimal;
import java.util.Collection;
import java.util.List;
import java.util.Map;

public interface LearningAssessmentService extends IService<LearningAssessment> {
    void enqueue(LearningRecord record, String courseId, String language, TaskContent content,
        Map<String, Object> answers, List<CourseMaterial> attachments);
    Map<String, Object> latest(String recordId);
    Map<String, Map<String, Object>> latestForRecords(Collection<String> recordIds);
    Map<String, Object> history(String recordId, int page);
    Map<String, Object> detail(String recordId, String id);
    Map<String, Object> retry(String recordId, String id);
    Map<String, Object> saveScore(String recordId, String id, BigDecimal score);
    void recoverProcessing();
    void processNext();
}
