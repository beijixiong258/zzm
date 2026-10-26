package zzm.dto;

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
        private int inputTokens;
        private int estimatedImageTokens;
    }
    @Data
    public static class PageInput {
        private int page;
        private String kind;
        private int textCharacters;
        private int width;
        private int height;
        private int originalWidth;
        private int originalHeight;
        private boolean cropped;
        private float renderDpi;
        private int cropLeft;
        private int cropTop;
        private int imageBytes;
        private int imageTokensEstimated;
        private String status = "prepared";
    }
    @Data
    public static class Report {
        private String currentUnit = "";
        // An absent mode identifies a legacy PDF transcription that must be reprocessed.
        private String pdfInputMode = "";
        private int unitsInspected;
        private int imageInputTokensEstimated;
        private List<PageInput> pageInputs = new ArrayList<>();
        private int schemaVersion = 2;
        private int unitsTotal;
        private int unitsProcessed;
        private int visionUnits;
        private int nativeTextUnits;
        private int visionInputTokensEstimated;
        private int visionPromptTokensActual;
        private int textTokensEstimated;
        private int textTokensUpperBound;
        private int textCharacters;
        private boolean truncated;
        private boolean visualReviewRequired;
        private List<String> failedUnits = new ArrayList<>();
        private List<String> notes = new ArrayList<>();
    }
}
