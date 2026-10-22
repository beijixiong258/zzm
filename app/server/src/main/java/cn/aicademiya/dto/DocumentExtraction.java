package cn.aicademiya.dto;

import lombok.Data;
import java.util.ArrayList;
import java.util.List;

@Data
public class DocumentExtraction {
    private String text = "";
    private String status = "failed";
    private String warning = "";
    private Report report = new Report();

    @Data
    public static class VisualReading {
        private boolean readable;
        private String text = "";
        private List<String> issues = new ArrayList<>();
    }
    @Data
    public static class Report {
        private int schemaVersion = 2;
        private int unitsTotal;
        private int unitsProcessed;
        private int visionUnits;
        private boolean truncated;
        private boolean visualReviewRequired;
        private List<String> failedUnits = new ArrayList<>();
        private List<String> notes = new ArrayList<>();
    }
}
