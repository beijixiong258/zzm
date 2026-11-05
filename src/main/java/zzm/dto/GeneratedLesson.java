package zzm.dto;

import lombok.Getter;
import lombok.Setter;

/** Model output includes inferred task fields, applied to the existing session columns. */
@Getter
@Setter
public class GeneratedLesson extends TaskContent {
    private String taskTitle = "";
    private String teachingLanguage = "";
    private String sessionType = "";
    private String taskInstructions = "";
}
