package A704.DODREAM.quiz.controller;

import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import A704.DODREAM.auth.dto.request.UserPrincipal;
import A704.DODREAM.quiz.dto.GradingResultDto;
import A704.DODREAM.quiz.dto.QuizDto;
import A704.DODREAM.quiz.dto.QuizSaveDto;
import A704.DODREAM.quiz.dto.QuizSubmissionDto;
import A704.DODREAM.quiz.dto.StudentMaterialStatsDto;
import A704.DODREAM.quiz.dto.StudentOverallStatsDto;
import A704.DODREAM.quiz.service.QuizService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;

@Tag(name = "Quiz API", description = "퀴즈 생성, 저장, 채점 API")
@RestController
@RequestMapping("/api/materials")
@RequiredArgsConstructor
public class QuizController {

	private final QuizService quizService;
    private final A704.DODREAM.quiz.grading.GradingAttemptService grading;

	@Operation(summary = "퀴즈 저장", description = "AI가 생성한 퀴즈를 검토 후 최종 저장합니다.")
	@PostMapping("/{materialId}/quizzes")
	public ResponseEntity<Void> saveQuizzes(
		@PathVariable Long materialId,
		@RequestBody List<QuizSaveDto> quizzes, // (수정) QuizDto -> QuizSaveDto
		@AuthenticationPrincipal UserPrincipal userPrincipal
	) {
		quizService.saveQuizzes(materialId, userPrincipal.userId(), quizzes);
		return ResponseEntity.ok().build();
	}

	@Operation(summary = "퀴즈 목록 조회", description = "해당 자료의 퀴즈 목록을 불러옵니다.")
	@GetMapping("/{materialId}/quizzes")
	public ResponseEntity<List<?>> getQuizzes(@PathVariable Long materialId, @AuthenticationPrincipal UserPrincipal actor) {
		return ResponseEntity.ok(quizService.getQuizzes(materialId, actor.userId()));
	}

	@Operation(summary = "퀴즈 채점 및 제출", description = "학생이 푼 답안을 제출하고 AI 채점 결과를 받습니다.")
	@PostMapping("/{materialId}/quizzes/submit")
    public ResponseEntity<?> submitQuiz(
        @PathVariable Long materialId,
        @RequestBody com.fasterxml.jackson.databind.JsonNode submission,
        @AuthenticationPrincipal UserPrincipal userPrincipal,
        HttpServletRequest request) {
        return grading.submit(userPrincipal.userId(), materialId, request.getHeader("Idempotency-Key"), submission, request.getHeader("Authorization"));
    }
    @GetMapping("/{materialId}/quiz-attempts/{attemptId}")
    public ResponseEntity<?> attempt(@PathVariable Long materialId, @PathVariable String attemptId,
        @AuthenticationPrincipal UserPrincipal actor) {
        return grading.status(actor.userId(), materialId, attemptId);
    }
    @PostMapping("/{materialId}/quiz-attempts/{attemptId}/retry")
    public ResponseEntity<?> retry(@PathVariable Long materialId, @PathVariable String attemptId,
        @RequestBody com.fasterxml.jackson.databind.JsonNode body, @AuthenticationPrincipal UserPrincipal actor,
        HttpServletRequest request) {
        return grading.retry(actor.userId(), materialId, attemptId, body, request.getHeader("Authorization"));
    }

	@Operation(summary = "나의 풀이 기록 조회", description = "이전에 푼 퀴즈의 채점 결과를 조회합니다.")
	@GetMapping("/{materialId}/quizzes/history")
	public ResponseEntity<List<GradingResultDto>> getQuizHistory(
		@PathVariable Long materialId,
		@AuthenticationPrincipal UserPrincipal userPrincipal
	) {
		return ResponseEntity.ok(quizService.getStudentLogs(materialId, userPrincipal.userId()));
	}
}
