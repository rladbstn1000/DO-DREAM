package A704.DODREAM.report.service;

import A704.DODREAM.material.entity.Material;
import A704.DODREAM.material.repository.MaterialRepository;
import A704.DODREAM.report.dto.LearningAnalysisResponse;
import A704.DODREAM.report.dto.SectionAccessLogRequest;
import A704.DODREAM.report.entity.SectionAccessLog;
import A704.DODREAM.report.entity.SectionDifficultyAnalysis;
import A704.DODREAM.report.repository.SectionAccessLogRepository;
import A704.DODREAM.report.repository.SectionDifficultyAnalysisRepository;
import A704.DODREAM.user.entity.User;
import A704.DODREAM.user.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.util.*;
import java.util.stream.Collectors;

/**
 * 시각 장애인 학생들의 학습 패턴을 분석하는 서비스
 * TTS 기반 학습에서 반복 청취 패턴을 분석하여 어려워하는 부분을 식별
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class LearningAnalysisService {

    private final SectionAccessLogRepository sectionAccessLogRepository;
    private final SectionDifficultyAnalysisRepository difficultyAnalysisRepository;
    private final UserRepository userRepository;
    private final MaterialRepository materialRepository;

    private static final int DIFFICULTY_THRESHOLD_REPEAT_COUNT = 3; // 3회 이상 반복시 어려운 것으로 판단
    private static final double DIFFICULTY_SCORE_THRESHOLD = 0.5; // 난이도 점수 임계값

    /**
     * Section 접근 로그를 기록
     */
    @Transactional
    public void logSectionAccess(Long studentId, SectionAccessLogRequest request) {
        User student = userRepository.findById(studentId)
            .orElseThrow(() -> new IllegalArgumentException("학생을 찾을 수 없습니다."));

        Material material = materialRepository.findById(request.getMaterialId())
            .orElseThrow(() -> new IllegalArgumentException("교재를 찾을 수 없습니다."));

        SectionAccessLog accessLog = SectionAccessLog.builder()
            .student(student)
            .material(material)
            .chapterId(request.getChapterId())
            .sectionIndex(request.getSectionIndex())
            .sectionType(request.getSectionType())
            .playMode(request.getPlayMode())
            .durationSeconds(request.getDurationSeconds())
            .completed(request.getCompleted())
            .build();

        sectionAccessLogRepository.save(accessLog);
        log.info("Section 접근 로그 저장: studentId={}, materialId={}, chapterId={}, sectionIndex={}",
            studentId, request.getMaterialId(), request.getChapterId(), request.getSectionIndex());
    }

    /**
     * 학생의 특정 교재에 대한 학습 패턴 분석
     */
    @Transactional(readOnly = true)
    public LearningAnalysisResponse analyzeLearningPattern(Long studentId, Long materialId) {
        User student = userRepository.findById(studentId)
            .orElseThrow(() -> new IllegalArgumentException("학생을 찾을 수 없습니다."));

        Material material = materialRepository.findById(materialId)
            .orElseThrow(() -> new IllegalArgumentException("교재를 찾을 수 없습니다."));

        List<SectionAccessLog> logs = sectionAccessLogRepository.findByStudentIdAndMaterialId(studentId, materialId);

        if (logs.isEmpty()) {
            return createEmptyAnalysis(material);
        }

        // 챕터별 분석
        List<LearningAnalysisResponse.ChapterAnalysis> chapterAnalyses = analyzeByChapter(logs);

        // 어려워하는 섹션 식별
        List<LearningAnalysisResponse.DifficultSection> difficultSections = identifyDifficultSections(logs);

        // 학습 패턴 요약
        LearningAnalysisResponse.LearningPatternSummary patternSummary = summarizeLearningPattern(logs, difficultSections);

        // 전체 완료율 계산
        double overallCompletionRate = calculateOverallCompletionRate(logs);

        return LearningAnalysisResponse.builder()
            .materialId(materialId)
            .materialTitle(material.getTitle())
            .totalChapters(chapterAnalyses.size())
            .completedChapters(calculateCompletedChapters(chapterAnalyses))
            .overallCompletionRate(overallCompletionRate)
            .chapterAnalyses(chapterAnalyses)
            .difficultSections(difficultSections)
            .patternSummary(patternSummary)
            .build();
    }

    /**
     * 챕터별 학습 패턴 분석
     */
    private List<LearningAnalysisResponse.ChapterAnalysis> analyzeByChapter(List<SectionAccessLog> logs) {
        Map<Integer, List<SectionAccessLog>> chapterLogsMap = logs.stream()
            .collect(Collectors.groupingBy(SectionAccessLog::getChapterId));

        return chapterLogsMap.entrySet().stream()
            .map(entry -> {
                Integer chapterId = entry.getKey();
                List<SectionAccessLog> chapterLogs = entry.getValue();

                // 접근한 고유 섹션 수
                long accessedSections = chapterLogs.stream()
                    .map(SectionAccessLog::getSectionIndex)
                    .distinct()
                    .count();

                // 완료한 섹션 수
                long completedSections = chapterLogs.stream()
                    .filter(SectionAccessLog::getCompleted)
                    .map(SectionAccessLog::getSectionIndex)
                    .distinct()
                    .count();

                // 총 접근 횟수
                int totalAccessCount = chapterLogs.size();

                // 평균 반복 횟수
                double averageRepeatCount = accessedSections > 0 ?
                    (double) totalAccessCount / accessedSections : 0.0;

                // 완료율
                double completionRate = accessedSections > 0 ?
                    (double) completedSections / accessedSections : 0.0;

                return LearningAnalysisResponse.ChapterAnalysis.builder()
                    .chapterId(chapterId)
                    .chapterTitle("Chapter " + chapterId)
                    .totalSections((int) accessedSections)
                    .accessedSections((int) accessedSections)
                    .completionRate(completionRate)
                    .totalAccessCount(totalAccessCount)
                    .averageRepeatCount(averageRepeatCount)
                    .build();
            })
            .sorted(Comparator.comparing(LearningAnalysisResponse.ChapterAnalysis::getChapterId))
            .collect(Collectors.toList());
    }

    /**
     * 어려워하는 섹션 식별 (반복 횟수가 많은 섹션)
     */
    private List<LearningAnalysisResponse.DifficultSection> identifyDifficultSections(List<SectionAccessLog> logs) {
        // 챕터-섹션별 로그 그룹화
        Map<String, List<SectionAccessLog>> sectionLogsMap = logs.stream()
            .collect(Collectors.groupingBy(log ->
                log.getChapterId() + "-" + log.getSectionIndex()));

        return sectionLogsMap.entrySet().stream()
            .map(entry -> {
                String key = entry.getKey();
                List<SectionAccessLog> sectionLogs = entry.getValue();

                int repeatCount = sectionLogs.size();
                int totalDuration = sectionLogs.stream()
                    .mapToInt(log -> log.getDurationSeconds() != null ? log.getDurationSeconds() : 0)
                    .sum();

                // 반복 횟수가 임계값 이상인 경우만 포함
                if (repeatCount < DIFFICULTY_THRESHOLD_REPEAT_COUNT) {
                    return null;
                }

                SectionAccessLog firstLog = sectionLogs.get(0);
                String difficultyReason = determineDifficultyReason(sectionLogs);

                return LearningAnalysisResponse.DifficultSection.builder()
                    .chapterId(firstLog.getChapterId())
                    .chapterTitle("Chapter " + firstLog.getChapterId())
                    .sectionIndex(firstLog.getSectionIndex())
                    .sectionType(firstLog.getSectionType())
                    .repeatCount(repeatCount)
                    .totalDurationSeconds(totalDuration)
                    .difficultyReason(difficultyReason)
                    .build();
            })
            .filter(Objects::nonNull)
            .sorted(Comparator.comparing(LearningAnalysisResponse.DifficultSection::getRepeatCount).reversed())
            .collect(Collectors.toList());
    }

    /**
     * 어려움의 원인 판단
     */
    private String determineDifficultyReason(List<SectionAccessLog> sectionLogs) {
        int repeatCount = sectionLogs.size();
        long incompleteCount = sectionLogs.stream()
            .filter(log -> !log.getCompleted())
            .count();

        String sectionType = sectionLogs.get(0).getSectionType();

        if (incompleteCount > repeatCount * 0.7) {
            return "섹션을 끝까지 듣지 못하고 반복 재생이 많음";
        } else if (repeatCount >= 5) {
            return "매우 높은 반복 재생 횟수 (" + repeatCount + "회)";
        } else if ("formula".equals(sectionType)) {
            return "수식 내용으로 이해가 어려울 수 있음";
        } else if ("image_description".equals(sectionType)) {
            return "이미지 설명으로 시각적 이해가 필요한 내용";
        } else {
            return "반복 청취가 필요한 복잡한 내용";
        }
    }

    /**
     * 학습 패턴 요약
     */
    private LearningAnalysisResponse.LearningPatternSummary summarizeLearningPattern(
        List<SectionAccessLog> logs,
        List<LearningAnalysisResponse.DifficultSection> difficultSections) {

        // 섹션 타입별 통계
        Map<String, Long> sectionTypeCount = logs.stream()
            .collect(Collectors.groupingBy(
                log -> log.getSectionType() != null ? log.getSectionType() : "unknown",
                Collectors.counting()
            ));

        // 가장 많이 반복한 섹션 타입 (어려워하는 타입)
        String mostDifficultType = sectionTypeCount.entrySet().stream()
            .max(Map.Entry.comparingByValue())
            .map(Map.Entry::getKey)
            .orElse("분석 데이터 부족");

        // 평균 완료율
        double averageCompletionRate = logs.stream()
            .filter(SectionAccessLog::getCompleted)
            .count() / (double) Math.max(logs.size(), 1);

        // 총 학습 시간 (분)
        int totalStudyTimeMinutes = logs.stream()
            .mapToInt(log -> log.getDurationSeconds() != null ? log.getDurationSeconds() : 0)
            .sum() / 60;

        // 선호하는 재생 모드
        String preferredPlayMode = logs.stream()
            .collect(Collectors.groupingBy(
                log -> log.getPlayMode() != null ? log.getPlayMode() : "unknown",
                Collectors.counting()
            ))
            .entrySet().stream()
            .max(Map.Entry.comparingByValue())
            .map(Map.Entry::getKey)
            .orElse("single");

        // 학습 개선 제안 생성
        List<String> recommendations = generateRecommendations(
            mostDifficultType, averageCompletionRate, difficultSections, preferredPlayMode);

        return LearningAnalysisResponse.LearningPatternSummary.builder()
            .mostDifficultSectionType(getSectionTypeKoreanName(mostDifficultType))
            .averageCompletionRate(averageCompletionRate)
            .totalStudyTimeMinutes(totalStudyTimeMinutes)
            .preferredPlayMode(getPlayModeKoreanName(preferredPlayMode))
            .recommendations(recommendations)
            .build();
    }

    /**
     * 학습 개선 제안 생성
     */
    private List<String> generateRecommendations(
        String mostDifficultType,
        double averageCompletionRate,
        List<LearningAnalysisResponse.DifficultSection> difficultSections,
        String preferredPlayMode) {

        List<String> recommendations = new ArrayList<>();

        // 완료율 기반 제안
        if (averageCompletionRate < 0.5) {
            recommendations.add("섹션 완료율이 낮습니다. 재생 속도를 낮춰보는 것을 권장합니다.");
        }

        // 어려운 섹션 타입 기반 제안
        if ("formula".equals(mostDifficultType)) {
            recommendations.add("수식 내용에 어려움을 겪고 있습니다. 수식 설명을 반복해서 듣거나 교사에게 추가 설명을 요청하세요.");
        } else if ("image_description".equals(mostDifficultType)) {
            recommendations.add("이미지 설명 부분에서 반복이 많습니다. 시각적 내용에 대한 추가 설명이 도움이 될 수 있습니다.");
        }

        // 재생 모드 기반 제안
        if ("single".equals(preferredPlayMode) && !difficultSections.isEmpty()) {
            recommendations.add("한 섹션씩 재생 모드를 사용 중입니다. 익숙해지면 연속 재생 모드를 사용해보세요.");
        } else if ("repeat".equals(preferredPlayMode)) {
            recommendations.add("반복 재생 모드를 자주 사용합니다. 어려운 부분은 북마크 기능을 활용해 나중에 다시 들어보세요.");
        }

        // 어려운 섹션 기반 제안
        if (difficultSections.size() > 5) {
            recommendations.add("여러 섹션에서 반복 청취가 많습니다. 교사에게 해당 부분에 대한 추가 학습 자료를 요청하는 것을 권장합니다.");
        }

        // 기본 제안
        if (recommendations.isEmpty()) {
            recommendations.add("학습을 잘 진행하고 있습니다. 꾸준히 학습하세요!");
        }

        return recommendations;
    }

    /**
     * 난이도 분석 실행 및 저장 (배치 작업으로 주기적 실행)
     */
    @Transactional
    public void performDifficultyAnalysis(Long studentId, Long materialId) {
        User student = userRepository.findById(studentId)
            .orElseThrow(() -> new IllegalArgumentException("학생을 찾을 수 없습니다."));

        Material material = materialRepository.findById(materialId)
            .orElseThrow(() -> new IllegalArgumentException("교재를 찾을 수 없습니다."));

        List<SectionAccessLog> logs = sectionAccessLogRepository.findByStudentIdAndMaterialId(studentId, materialId);

        // 챕터-섹션별 로그 그룹화
        Map<String, List<SectionAccessLog>> sectionLogsMap = logs.stream()
            .collect(Collectors.groupingBy(log ->
                log.getChapterId() + "-" + log.getSectionIndex()));

        LocalDate today = LocalDate.now();

        sectionLogsMap.forEach((key, sectionLogs) -> {
            SectionAccessLog firstLog = sectionLogs.get(0);

            int repeatCount = sectionLogs.size();
            int totalDuration = sectionLogs.stream()
                .mapToInt(log -> log.getDurationSeconds() != null ? log.getDurationSeconds() : 0)
                .sum();

            long completedCount = sectionLogs.stream()
                .filter(SectionAccessLog::getCompleted)
                .count();
            double completionRate = (double) completedCount / repeatCount;

            SectionDifficultyAnalysis analysis = SectionDifficultyAnalysis.builder()
                .student(student)
                .material(material)
                .chapterId(firstLog.getChapterId())
                .sectionIndex(firstLog.getSectionIndex())
                .sectionType(firstLog.getSectionType())
                .repeatCount(repeatCount)
                .totalDurationSeconds(totalDuration)
                .completionRate(completionRate)
                .analysisDate(today)
                .build();

            analysis.calculateDifficultyScore();
            difficultyAnalysisRepository.save(analysis);
        });

        log.info("난이도 분석 완료: studentId={}, materialId={}, 분석된 섹션 수={}",
            studentId, materialId, sectionLogsMap.size());
    }

    /**
     * 빈 분석 결과 생성
     */
    private LearningAnalysisResponse createEmptyAnalysis(Material material) {
        return LearningAnalysisResponse.builder()
            .materialId(material.getId())
            .materialTitle(material.getTitle())
            .totalChapters(0)
            .completedChapters(0)
            .overallCompletionRate(0.0)
            .chapterAnalyses(Collections.emptyList())
            .difficultSections(Collections.emptyList())
            .patternSummary(LearningAnalysisResponse.LearningPatternSummary.builder()
                .mostDifficultSectionType("분석 데이터 없음")
                .averageCompletionRate(0.0)
                .totalStudyTimeMinutes(0)
                .preferredPlayMode("single")
                .recommendations(List.of("학습을 시작하세요!"))
                .build())
            .build();
    }

    /**
     * 전체 완료율 계산
     */
    private double calculateOverallCompletionRate(List<SectionAccessLog> logs) {
        long totalSections = logs.stream()
            .map(log -> log.getChapterId() + "-" + log.getSectionIndex())
            .distinct()
            .count();

        long completedSections = logs.stream()
            .filter(SectionAccessLog::getCompleted)
            .map(log -> log.getChapterId() + "-" + log.getSectionIndex())
            .distinct()
            .count();

        return totalSections > 0 ? (double) completedSections / totalSections : 0.0;
    }

    /**
     * 완료된 챕터 수 계산
     */
    private int calculateCompletedChapters(List<LearningAnalysisResponse.ChapterAnalysis> chapterAnalyses) {
        return (int) chapterAnalyses.stream()
            .filter(chapter -> chapter.getCompletionRate() >= 0.8) // 80% 이상 완료시
            .count();
    }

    /**
     * 섹션 타입 한글 이름 반환
     */
    private String getSectionTypeKoreanName(String sectionType) {
        return switch (sectionType) {
            case "paragraph" -> "본문";
            case "heading" -> "제목";
            case "formula" -> "수식";
            case "image_description" -> "이미지 설명";
            default -> "기타";
        };
    }

    /**
     * 재생 모드 한글 이름 반환
     */
    private String getPlayModeKoreanName(String playMode) {
        return switch (playMode) {
            case "single" -> "한 섹션씩";
            case "continuous" -> "연속 재생";
            case "repeat" -> "반복 재생";
            default -> "단일 재생";
        };
    }
}

