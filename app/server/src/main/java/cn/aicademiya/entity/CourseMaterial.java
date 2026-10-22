package cn.aicademiya.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

@Data
public class CourseMaterial {
    @TableId(type = IdType.ASSIGN_UUID)
    private String id;
    private String courseId;
    private String title;
    private String fileName;
    private String relativePath;
    private String mimeType;
    private String storagePath;
    private String textContent;
    private String extractionReportJson;
    private String status;
    private String visibility;
    private String errorMessage;
    private Boolean archived;
    private java.time.LocalDateTime createdAt;
}
