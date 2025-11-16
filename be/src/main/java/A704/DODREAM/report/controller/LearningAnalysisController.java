package A704.DODREAM.report.controller;

import A704.DODREAM.global.response.ApiResponse;
import A704.DODREAM.report.dto.LearningAnalysisResponse;
import A704.DODREAM.report.dto.SectionAccessLogRequest;
import A704.DODREAM.report.service.LearningAnalysisService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

/**
 * 시각 장애인 학생의 학습 분석 API
 * TTS 기반 학습에서 반복 청취 패턴을 분석하여 학습 난이도와 개선 방안 제시
 */
@Slf4j
@RestController
@RequestMapping("/api/learning-analysis")
@RequiredArgsConstructor
@Tag(name = "학습 분석", description = "학습 패턴 분석 및 난이도 분석 API")
public class LearningAnalysisController {

    private final LearningAnalysisService learningAnalysisService;

    /**
     * Section 접근 로그 기록
     * 프론트엔드에서 학생이 Section을 재생할 때마다 호출
     */
    @PostMapping("/log")
    @Operation(summary = "Section 접근 로그 기록", description = "학생이 Section을 재생할 때마다 로그를 기록합니다.")
    public ResponseEntity<ApiResponse<Void>> logSectionAccess(
        Authentication authentication,
        @RequestBody SectionAccessLogRequest request) {

        Long studentId = Long.parseLong(authentication.getName());
        learningAnalysisService.logSectionAccess(studentId, request);

        return ResponseEntity.ok(
            ApiResponse.success("로그가 성공적으로 기록되었습니다.", HttpStatus.OK, null)
        );
    }

    /**
     * 학생의 특정 교재에 대한 학습 패턴 분석
     */
    @GetMapping("/material/{materialId}")
    @Operation(summary = "학습 패턴 분석", description = "학생의 특정 교재에 대한 학습 패턴을 분석합니다.")
    public ResponseEntity<ApiResponse<LearningAnalysisResponse>> analyzeLearningPattern(
        Authentication authentication,
        @Parameter(description = "교재 ID", required = true)
        @PathVariable Long materialId) {

        Long studentId = Long.parseLong(authentication.getName());
        LearningAnalysisResponse analysis = learningAnalysisService.analyzeLearningPattern(studentId, materialId);

        return ResponseEntity.ok(
            ApiResponse.success("학습 패턴 분석이 완료되었습니다.", HttpStatus.OK, analysis)
        );
    }

    /**
     * 난이도 분석 실행 (관리자 또는 배치 작업용)
     */
    @PostMapping("/difficulty-analysis/{studentId}/{materialId}")
    @Operation(summary = "난이도 분석 실행", description = "특정 학생의 교재에 대한 난이도 분석을 실행합니다. (관리자용)")
    public ResponseEntity<ApiResponse<Void>> performDifficultyAnalysis(
        @Parameter(description = "학생 ID", required = true)
        @PathVariable Long studentId,
        @Parameter(description = "교재 ID", required = true)
        @PathVariable Long materialId) {

        learningAnalysisService.performDifficultyAnalysis(studentId, materialId);

        return ResponseEntity.ok(
            ApiResponse.success("난이도 분석이 완료되었습니다.", HttpStatus.OK, null)
        );
    }
}

