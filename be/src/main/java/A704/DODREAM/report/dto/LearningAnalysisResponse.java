package A704.DODREAM.report.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * 학습 분석 결과를 반환하는 DTO
 */
@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class LearningAnalysisResponse {
    
    private Long materialId;
    private String materialTitle;
    private Integer totalChapters;
    private Integer completedChapters;
    private Double overallCompletionRate;
    
    private List<ChapterAnalysis> chapterAnalyses;
    private List<DifficultSection> difficultSections;
    private LearningPatternSummary patternSummary;
    
    @Getter
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class ChapterAnalysis {
        private Integer chapterId;
        private String chapterTitle;
        private Integer totalSections;
        private Integer accessedSections;
        private Double completionRate;
        private Integer totalAccessCount;
        private Double averageRepeatCount;
    }
    
    @Getter
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class DifficultSection {
        private Integer chapterId;
        private String chapterTitle;
        private Integer sectionIndex;
        private String sectionType;
        private Integer repeatCount;
        private Integer totalDurationSeconds;
        private String difficultyReason;
    }
    
    @Getter
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class LearningPatternSummary {
        private String mostDifficultSectionType; // 가장 어려워하는 섹션 타입
        private Double averageCompletionRate;
        private Integer totalStudyTimeMinutes;
        private String preferredPlayMode; // 선호하는 재생 모드
        private List<String> recommendations; // 학습 개선 제안
    }
}

