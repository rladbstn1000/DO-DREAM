package A704.DODREAM.quiz.service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.reactive.function.client.WebClient;

import A704.DODREAM.global.exception.CustomException;
import A704.DODREAM.global.exception.constant.ErrorCode;
import A704.DODREAM.material.entity.Material;
import A704.DODREAM.material.repository.MaterialRepository;
import A704.DODREAM.quiz.dto.GradingResultDto;
import A704.DODREAM.quiz.dto.QuizDto;
import A704.DODREAM.quiz.dto.QuizSaveDto;
import A704.DODREAM.quiz.dto.QuizSubmissionDto;
import A704.DODREAM.quiz.dto.StudentMaterialStatsDto;
import A704.DODREAM.quiz.dto.StudentOverallStatsDto;
import A704.DODREAM.quiz.entity.Quiz;
import A704.DODREAM.quiz.entity.StudentQuizLog;
import A704.DODREAM.quiz.repository.QuizRepository;
import A704.DODREAM.quiz.repository.StudentQuizLogRepository;
import A704.DODREAM.user.entity.User;
import A704.DODREAM.user.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

@Service
@Slf4j
@RequiredArgsConstructor
public class QuizService {
    private final A704.DODREAM.authorization.AuthorizationPolicy policy;

	private final QuizRepository quizRepository;
	private final StudentQuizLogRepository studentQuizLogRepository;
	private final MaterialRepository materialRepository;
	private final UserRepository userRepository;
	private final WebClient webClient;

	@Value("${fastapi.url}")
	private String fastApiUrl;

	/**
	 * 교사가 검토한 퀴즈 리스트를 최종 저장 (기존 퀴즈 덮어쓰기)
	 */
	@Transactional
	public void saveQuizzes(Long materialId, Long userId, List<QuizSaveDto> quizDtos) {
        policy.owned(userId, materialId); // (수정) 파라미터 타입 변경
		Material material = materialRepository.findById(materialId)
			.orElseThrow(() -> new CustomException(ErrorCode.FILE_NOT_FOUND));

		// 권한 체크
		if (!material.getTeacher().getId().equals(userId)) {
			throw new CustomException(ErrorCode.FORBIDDEN);
		}

        validateEdits(materialId, quizDtos);
        Map<Integer, Quiz> existing = quizRepository.findAllByMaterialIdOrderByQuestionNumber(materialId).stream()
            .collect(Collectors.toMap(Quiz::getQuestionNumber, q -> q));
        for (QuizSaveDto dto : quizDtos) {
            Quiz quiz = existing.remove(dto.getQuestionNumber());
            if (quiz == null) {
                quiz = Quiz.builder().material(material).questionNumber(dto.getQuestionNumber()).build();
            }
            quiz.edit(dto);
            quizRepository.save(quiz);
        }
        quizRepository.deleteAll(existing.values());
    }

    public void validateEdits(Long materialId, List<QuizSaveDto> quizzes) {
        if (quizzes == null) throw A704.DODREAM.authorization.AuthorizationPolicy.invalid();
        java.util.Set<Integer> numbers = new java.util.HashSet<>();
        for (QuizSaveDto quiz : quizzes) {
            if (quiz == null || quiz.getQuestionNumber() == null || quiz.getQuestionNumber() <= 0
                || !numbers.add(quiz.getQuestionNumber()) || quiz.getTitle() == null || quiz.getContent() == null
                || quiz.getCorrectAnswer() == null) throw A704.DODREAM.authorization.AuthorizationPolicy.invalid();
        }
        if (materialId != null) {
            for (Quiz quiz : quizRepository.findAllByMaterialIdOrderByQuestionNumber(materialId)) {
                if (!numbers.contains(quiz.getQuestionNumber()) && studentQuizLogRepository.existsByQuizId(quiz.getId()))
                    throw new A704.DODREAM.authorization.AuthorizationFailure(org.springframework.http.HttpStatus.CONFLICT);
            }
        }
    }

	/**
	 * 특정 자료의 퀴즈 목록 조회 (학생/교사 공용)
	 */
	@Transactional(readOnly = true)
    public List<?> getQuizzes(Long materialId, Long actorId) {
        policy.read(actorId, materialId);
        boolean teacher = policy.actor(actorId).getRole() == A704.DODREAM.user.entity.Role.TEACHER;
        return quizRepository.findAllByMaterialIdOrderByQuestionNumber(materialId).stream()
            .map(quiz -> teacher ? QuizDto.from(quiz) : A704.DODREAM.quiz.dto.StudentQuizDto.from(quiz)).toList();
    }

	/**
	 * 학생 답안 일괄 채점 및 로그 저장
	 */
	@Transactional
    public List<GradingResultDto> gradeAndLog(Long materialId, Long studentId, QuizSubmissionDto submission, String token) {
        policy.studentMaterial(studentId, materialId);
        User student = policy.role(studentId, A704.DODREAM.user.entity.Role.STUDENT);
        if (submission.getAnswers() == null || submission.getAnswers().isEmpty()) throw A704.DODREAM.authorization.AuthorizationPolicy.invalid();
        Map<Long, Quiz> quizMap = quizRepository.findAllByMaterialIdOrderByQuestionNumber(materialId).stream()
            .collect(Collectors.toMap(Quiz::getId, q -> q));
        Map<Long, String> submitted = new java.util.LinkedHashMap<>();
        for (var answer : submission.getAnswers()) {
            if (answer == null || answer.getQuizId() == null || answer.getAnswer() == null
                || !quizMap.containsKey(answer.getQuizId()) || submitted.putIfAbsent(answer.getQuizId(), answer.getAnswer()) != null)
                throw A704.DODREAM.authorization.AuthorizationPolicy.invalid();
        }
        List<Map<String, Object>> answers = submitted.entrySet().stream().map(entry -> Map.<String, Object>of(
            "question_id", entry.getKey(), "student_answer", entry.getValue())).toList();
        List<GradingResultDto> results = webClient.post().uri(fastApiUrl + "/rag/quiz/grade-batch")
            .header("Authorization", token).bodyValue(Map.of("material_id", materialId, "student_answers", answers))
            .retrieve().bodyToMono(new ParameterizedTypeReference<List<GradingResultDto>>() {}).block();
        if (results == null || results.size() != submitted.size()) throw new IllegalStateException("Invalid grading response");
        java.util.Set<Long> seen = new java.util.HashSet<>();
        List<StudentQuizLog> logs = new ArrayList<>();
        List<GradingResultDto> safeResults = new ArrayList<>();
        for (var result : results) {
            if (result == null || !submitted.containsKey(result.getQuizId()) || !seen.add(result.getQuizId()))
                throw new IllegalStateException("Invalid grading response");
            Quiz quiz = quizMap.get(result.getQuizId());
            String feedback = result.getAiFeedback() == null ? "" : result.getAiFeedback();
            logs.add(StudentQuizLog.builder().quiz(quiz).student(student).studentAnswer(submitted.get(quiz.getId()))
                .isCorrect(result.isCorrect()).aiFeedback(feedback).build());
            safeResults.add(GradingResultDto.builder().quizId(quiz.getId()).studentAnswer(submitted.get(quiz.getId()))
                .isCorrect(result.isCorrect()).aiFeedback(feedback).correctAnswer(quiz.getCorrectAnswer()).build());
        }
        studentQuizLogRepository.saveAll(logs);
        return safeResults;
    }

	/**
	 * 학생 퀴즈 풀이 기록 조회
	 */
	@Transactional(readOnly = true)
	public List<GradingResultDto> getStudentLogs(Long materialId, Long studentId) {
        policy.studentMaterial(studentId, materialId);
		return studentQuizLogRepository.findByStudentIdAndQuizMaterialId(studentId, materialId).stream()
			.map(log -> GradingResultDto.builder()
				.quizId(log.getQuiz().getId()).correctAnswer(log.getQuiz().getCorrectAnswer())
				.studentAnswer(log.getStudentAnswer())
				.isCorrect(log.isCorrect())
				.aiFeedback(log.getAiFeedback() == null ? "" : log.getAiFeedback())
				.build())
			.collect(Collectors.toList());
	}

	/**
	 * [API 1 수정] 특정 학생의 '모든 자료별' 퀴즈 성적 통계 리스트 조회
	 */
	@Transactional(readOnly = true)
	public List<StudentMaterialStatsDto> getStudentStatsByMaterialList(Long studentId, Long actorId) {
        policy.historySubject(actorId, studentId);
		List<StudentQuizLog> logs = studentQuizLogRepository.findAllByStudentIdWithMaterial(studentId).stream()
            .filter(log -> policy.historyVisible(actorId, studentId, log.getQuiz().getMaterial())).toList();

		if (logs.isEmpty()) {
			return new ArrayList<>();
		}

		Map<Long, List<StudentQuizLog>> logsByMaterial = logs.stream()
			.collect(Collectors.groupingBy(log -> log.getQuiz().getMaterial().getId()));

		List<StudentMaterialStatsDto> resultList = new ArrayList<>();

		for (Map.Entry<Long, List<StudentQuizLog>> entry : logsByMaterial.entrySet()) {
			Long materialId = entry.getKey();
			List<StudentQuizLog> materialLogs = entry.getValue();
			Material material = materialLogs.get(0).getQuiz().getMaterial();
			int totalQuizCount = quizRepository.countByMaterialId(materialId);

			if (totalQuizCount > 0) {
				// [로직 변경] 퀴즈 ID별로 가장 최근(Latest) 로그만 필터링
				Map<Long, StudentQuizLog> latestLogsByQuiz = materialLogs.stream()
					.collect(Collectors.toMap(
						log -> log.getQuiz().getId(), // Key: Quiz ID
						log -> log,                   // Value: Log 객체
						// Merge Function: 기존값과 새로운값 중 solvedAt이 더 늦은(큰) 것을 선택
						(existing, replacement) -> existing.getSolvedAt().isAfter(replacement.getSolvedAt()) ? existing : replacement
					));

				// 필터링된 최신 로그들 중에서 정답 개수 카운트
				long correctCount = latestLogsByQuiz.values().stream()
					.filter(StudentQuizLog::isCorrect)
					.count();

				double correctRate = (double) correctCount / totalQuizCount * 100.0;

				resultList.add(StudentMaterialStatsDto.builder()
					.materialId(materialId)
					.materialTitle(material.getTitle())
					.correctCount((int) correctCount)
					.tryCount(materialLogs.size()) // 시도 횟수는 전체 로그 수 그대로 유지 (노력 지표)
					.totalQuizCount(totalQuizCount)
					.correctRate(Math.round(correctRate * 10) / 10.0)
					.build());
			}
		}

		return resultList;
	}

	/**
	 * [API 2] 특정 학생의 종합 평균 정답률 조회
	 * (각 자료별 정답률을 구하고, 그 정답률들의 평균을 계산)
	 */
	@Transactional(readOnly = true)
	public StudentOverallStatsDto getStudentOverallStats(Long studentId, Long actorId) {
        policy.historySubject(actorId, studentId);
		List<StudentQuizLog> logs = studentQuizLogRepository.findAllByStudentIdWithMaterial(studentId).stream()
            .filter(log -> policy.historyVisible(actorId, studentId, log.getQuiz().getMaterial())).toList();

		if (logs.isEmpty()) {
			return StudentOverallStatsDto.builder()
				.studentId(studentId)
				.solvedMaterialCount(0)
				.averageCorrectRate(0.0)
				.build();
		}

		Map<Long, List<StudentQuizLog>> logsByMaterial = logs.stream()
			.collect(Collectors.groupingBy(log -> log.getQuiz().getMaterial().getId()));

		double sumOfRates = 0.0;
		int materialCount = 0;

		for (Long materialId : logsByMaterial.keySet()) {
			int totalQuizInMaterial = quizRepository.countByMaterialId(materialId);

			if (totalQuizInMaterial > 0) {
				List<StudentQuizLog> materialLogs = logsByMaterial.get(materialId);

				// [로직 변경] 퀴즈 ID별로 가장 최근 로그만 필터링
				long correctCount = materialLogs.stream()
					.collect(Collectors.toMap(
						log -> log.getQuiz().getId(),
						log -> log,
						(existing, replacement) -> existing.getSolvedAt().isAfter(replacement.getSolvedAt()) ? existing : replacement
					))
					.values().stream()
					.filter(StudentQuizLog::isCorrect)
					.count();

				double materialRate = (double) correctCount / totalQuizInMaterial * 100.0;
				sumOfRates += materialRate;
				materialCount++;
			}
		}

		double averageRate = materialCount > 0 ? sumOfRates / materialCount : 0.0;

		return StudentOverallStatsDto.builder()
			.studentId(studentId)
			.solvedMaterialCount(materialCount)
			.averageCorrectRate(Math.round(averageRate * 10) / 10.0)
			.build();
	}
}