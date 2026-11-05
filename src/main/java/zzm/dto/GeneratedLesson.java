package zzm.dto;

import lombok.Getter;
import lombok.Setter;

/** 模型输出包含推断的任务字段，应用到现有任务表的对应列。 */
@Getter
@Setter
public class GeneratedLesson extends TaskContent {
    private String taskTitle = "";
    private String teachingLanguage = "";
    private String sessionType = "";
    private String taskInstructions = "";
}
