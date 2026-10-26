package zzm.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

@Data
public class LearningRecord {
    @TableId(type = IdType.ASSIGN_UUID)
    private String id;
    private String sessionId;
    private String userId;
    private String versionId;
    private Boolean preview;
    private String snapshotJson;
    private String status;
    private String answersJson;
    private String answerHistoryJson;
    private String conversationHistoryJson;
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
