package cn.aicademiya.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

@Data
public class SessionVersion {
    @TableId(type = IdType.ASSIGN_UUID)
    private String id;
    private String sessionId;
    private String courseId;
    private Long revision;
    private String label;
    private String contentJson;
    private java.time.LocalDateTime createdAt;
}
