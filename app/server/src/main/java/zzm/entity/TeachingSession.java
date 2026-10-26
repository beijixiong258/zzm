package zzm.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

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
}
