package zzm.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import java.time.LocalDateTime;

@Data
public class LearningRecordHistory {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String recordId;
    private String kind;
    private String payloadJson;
    private Integer messageCount;
    private LocalDateTime createdAt;
}