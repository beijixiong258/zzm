package cn.aicademiya.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

@Data
public class GenerationJob {
    @TableId(type = IdType.ASSIGN_UUID)
    private String id;
    private String sessionId;
    private String ownerId;
    private String kind;
    private String status;
    private String stage;
    private Long expectedRevision;
    private String requestJson;
    private String resultJson;
    private String errorMessage;
    private java.time.LocalDateTime createdAt;
    private java.time.LocalDateTime updatedAt;
}
