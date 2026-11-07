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
    private LocalDateTime opensAt;
    @TableField(updateStrategy = FieldStrategy.NEVER)
    private LocalDateTime closesAt;

    public String availabilityStatus(LocalDateTime now) {
        if (Boolean.TRUE.equals(archived)) return "recycled";
        if (publishedVersionId == null) return "draft";
        if (!Boolean.TRUE.equals(available) || closesAt != null && !now.isBefore(closesAt)) return "expired";
        if (opensAt != null && now.isBefore(opensAt)) return "scheduled";
        return "open";
    }

    public boolean openAt(LocalDateTime now) {
        return "open".equals(availabilityStatus(now));
    }
}
