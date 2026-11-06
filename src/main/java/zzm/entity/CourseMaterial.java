package zzm.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import java.util.Locale;
import java.util.Objects;

@Data
public class CourseMaterial {
    @TableId(type = IdType.ASSIGN_UUID)
    private String id;
    private String courseId;
    private String ownerId;
    private String recordId;
    private String questionId;
    private String title;
    private String fileName;
    private String relativePath;
    private String mimeType;
    private String storagePath;
    private String textContent;
    private String extractionReportJson;
    @com.fasterxml.jackson.annotation.JsonIgnore
    private String retrievalJson;
    private java.time.LocalDateTime retrievalRetryAt;
    private String status;
    private String visibility;
    private String errorMessage;
    private Boolean archived;
    private Long fileSize;
    private java.time.LocalDateTime fileRemovedAt;
    private String removedBy;
    private String trashPath;
    private java.time.LocalDateTime createdAt;

    public boolean hasPdfFormat() {
        return "application/pdf".equalsIgnoreCase(mimeType)
            || Objects.toString(fileName, "").toLowerCase(Locale.ROOT).endsWith(".pdf");
    }
}
