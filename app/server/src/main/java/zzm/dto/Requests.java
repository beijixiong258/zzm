package zzm.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import lombok.Data;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public final class Requests {
    private Requests() {}
    @Data public static class StudentLogin {
        @NotBlank @Size(max = 64) private String username;
        @NotBlank @Size(max = 128) private String invitationCode;
    }
    @Data public static class StudentInvitation {
        @NotBlank @Size(max = 100) private String name;
        @NotBlank @Pattern(regexp = "[A-Za-z0-9_.-]{3,64}") private String username;
    }
    @Data public static class Login {
        @NotBlank @Email private String email;
        @NotBlank @Size(max = 128) private String password;
        @Pattern(regexp = "student|teacher|admin") private String role;
    }
    @Data public static class Account {
        @NotBlank @Size(max = 100) private String name;
        @NotBlank @Email @Size(max = 254) private String email;
        @Size(min = 8, max = 128) private String password;
        @NotBlank @Pattern(regexp = "student|teacher|admin") private String role = "student";
    }
    @Data public static class Password {
        @NotBlank private String currentPassword;
        @NotBlank @Size(min = 8, max = 128) private String newPassword;
    }
    @Data public static class AccountBatch {
        @NotNull @Size(min = 1, max = 1000) private List<@NotNull @Valid Account> members;
    }
    @Data public static class CourseInput {
        @NotBlank @Size(max = 300) private String title;
        @NotBlank @Size(max = 100) private String code;
        @NotNull @Size(max = 10000) private String description = "";
        @NotNull @Size(max = 20000) private String courseInformation = "";
        @NotNull @Size(max = 20000) private String studentProfile = "";
        @NotNull @Size(max = 20000) private String systemInstructions = "";
    }
    @Data public static class SessionInput {
        @NotBlank @Size(max = 300) private String title;
        @NotNull @Size(max = 10000) private String description = "";
        @NotBlank @Pattern(regexp = "tutor|assignment") private String sessionType = "tutor";
        @NotNull @Size(max = 10000) private String topic = "";
        @NotNull @Size(max = 20000) private String learningGoals = "";
        @NotNull @Size(max = 20000) private String additionalInstructions = "";
        @NotBlank @Pattern(regexp = "zh-CN|en") private String teachingLanguage = "zh-CN";
        @NotNull @Size(max = 100) private List<String> materialIds = new ArrayList<>();
        @NotNull @Valid private TaskContent content = new TaskContent();
        @NotNull @Min(0) private Long revision = 0L;
    }
    @Data public static class Revision {
        @NotNull @Min(0) private Long revision;
    }
    @Data public static class Generation {
        @NotNull @Min(0) private Long revision;
        @NotBlank @Pattern(regexp = "generate|import|revise") private String kind = "generate";
        @Size(max = 10000) private String instruction = "";
        @Size(max = 64) private String sourceMaterialId;
        @NotNull @Size(max = 100) private List<@NotBlank String> sourceMaterialIds = new ArrayList<>();
    }
    @Data public static class Answer {
        @NotNull private Long revision;
        @NotNull @Size(max = 100) private Map<String, String> answers;
    }
    @Data public static class Chat {
        @Size(max = 100) private Map<@Size(max = 100) String, @Size(max = 20000) String> answers;
        @NotBlank @Size(max = 10000) private String message;
        @NotBlank @Size(max = 100) private String requestId;
        private Long revision;
        @NotNull @Size(max = 20) private List<String> attachmentIds = new ArrayList<>();
        @Size(max = 64) private String courseId;
        @NotNull @Size(max = 1000) private List<@NotNull @Valid ChatMessage> history = new ArrayList<>();
    }
    @Data public static class ChatMessage {
        @NotBlank @Pattern(regexp = "user|assistant") private String role;
        @NotBlank @Size(max = 20000) private String content;
        private String requestId;
        private String createdAt;
        private List<String> attachmentIds = new ArrayList<>();
        private Map<String, Object> usage;
        private boolean pendingReview;
        private String originalContent;
        private String reviewedBy;
        private String reviewedAt;
    }
    @Data public static class Review {
        @NotNull private Long revision;
        @NotBlank @Pattern(regexp = "confirmed|needsRevision") private String status;
        @NotNull @Size(max = 10000) private String teacherNote = "";
    }
    @Data public static class MaterialInput {
        @NotBlank @Size(max = 300) private String title;
        @NotBlank @Pattern(regexp = "student|teacher") private String visibility;
    }
}
