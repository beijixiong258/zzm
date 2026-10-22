package cn.aicademiya.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

@Data
public class LearningRecord {
    @TableId(type = IdType.ASSIGN_UUID)
    private String id;
    private String sessionId;
    private String userId;
    private String versionId;
    private String status;
    private String answersJson;
    private String messagesJson;
    private String legacyJson;
    @Version
    private Long revision;
    private java.time.LocalDateTime startedAt;
    private java.time.LocalDateTime updatedAt;
    private java.time.LocalDateTime submittedAt;
    private java.time.LocalDateTime reviewedAt;
    private String teacherNote;
}
