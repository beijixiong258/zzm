package zzm.dto;

import lombok.Data;
import java.util.*;

/** 学习记录的派生记忆，与原始消息一同通过乐观锁保存，不作为题目和作答的事实来源。 */
@Data
public class TutorState {
    private String conversationId = UUID.randomUUID().toString();
    private String contentFingerprint = "";
    private int coveredMessages;
    private String coveredFingerprint = "";
    private String summary = "";
    private List<String> questionIds = new ArrayList<>();
    private String topic = "";
    private List<Map<String, Object>> sources = new ArrayList<>();
}
