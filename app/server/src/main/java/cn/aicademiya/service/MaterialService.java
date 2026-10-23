package cn.aicademiya.service;

import cn.aicademiya.dto.Requests;
import cn.aicademiya.entity.*;
import com.baomidou.mybatisplus.spring.service.IService;
import org.springframework.web.multipart.MultipartFile;
import java.util.*;

public interface MaterialService extends IService<CourseMaterial> {
    List<Map<String, Object>> library(String courseId, AccountUser user);
    CourseMaterial upload(String courseId, MultipartFile file, String relativePath, String visibility, AccountUser user);
    CourseMaterial uploadForRecord(String courseId, String recordId, String questionId, org.springframework.web.multipart.MultipartFile file, AccountUser user);
    CourseMaterial requireFile(String id, String versionId, AccountUser user);
    void edit(String id, Requests.MaterialInput input, AccountUser user);
    void archive(String id, boolean archived, AccountUser user);
    void retry(String id, AccountUser user);
    void recoverProcessing();
    void processNext();
    void recycleRemovedAttachments();
    void reportStorageUsage();
    void requireProcessed(List<CourseMaterial> materials);
    List<CourseMaterial> selected(String courseId, List<String> ids);
    Map<String, Object> view(CourseMaterial material);
}
