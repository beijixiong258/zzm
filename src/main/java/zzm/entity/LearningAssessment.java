package zzm.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import lombok.Data;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Data
public class LearningAssessment {
    @TableId(type = IdType.ASSIGN_UUID)
    private String id;
    private String recordId;
    private Long submissionRevision;
    private String status;
    private String inputJson;
    private String feedbackJson;
    private String runId;
    private Integer questionCount;
    private Integer evaluatedCount;
    private LocalDateTime submittedAt;
    private LocalDateTime updatedAt;
    private LocalDateTime evaluatedAt;
    private BigDecimal teacherScore;
    private LocalDateTime scoredAt;
}
