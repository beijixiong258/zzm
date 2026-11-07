package zzm.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import java.time.LocalDateTime;

@Data
public class TeachingSession {
    @TableId(type = IdType.ASSIGN_UUID)
    private String id;
    private String courseId;
    private String title;
    private String description;
    private String sessionType;
    private String topic;
    private String learningGoals;
    private String additionalInstructions;
    private String teachingLanguage;
    private String materialIdsJson;
    private String contentJson;
    @Version
    private Long revision;
    private String publishedVersionId;
    private Boolean archived;
    @TableField(updateStrategy = FieldStrategy.NEVER)
    private Boolean available;
    @TableField(updateStrategy = FieldStrategy.NEVER)
    private LocalDateTime closesAt;
    private LocalDateTime updatedAt;

    public String availabilityStatus(LocalDateTime now) {
        if (Boolean.TRUE.equals(archived)) return "recycled";
        if (publishedVersionId == null) return "draft";
        if (closesAt != null && !now.isBefore(closesAt)) return "expired";
        if (!Boolean.TRUE.equals(available)) return "closed";
        return "open";
    }

    public boolean openAt(LocalDateTime now) {
        return "open".equals(availabilityStatus(now));
    }
}
