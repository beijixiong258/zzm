package cn.aicademiya.service;

import cn.aicademiya.dto.Requests;
import cn.aicademiya.entity.*;
import com.baomidou.mybatisplus.extension.service.IService;
import org.springframework.web.multipart.MultipartFile;
import java.util.*;

public interface MaterialService extends IService<CourseMaterial> {
    List<Map<String, Object>> library(String courseId, AccountUser user);
    CourseMaterial upload(String courseId, MultipartFile file, String relativePath, String visibility, AccountUser user);
    CourseMaterial requireFile(String id, String versionId, AccountUser user);
    void edit(String id, Requests.MaterialInput input, AccountUser user);
    void archive(String id, boolean archived, AccountUser user);
    void retry(String id, AccountUser user);
    void recoverProcessing();
    void processNext();
    void requireProcessed(List<CourseMaterial> materials);
    List<CourseMaterial> selected(String courseId, List<String> ids);
    Map<String, Object> view(CourseMaterial material);
}
