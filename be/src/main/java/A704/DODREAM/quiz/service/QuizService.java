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
	private final org.springframework.jdbc.core.JdbcTemplate gradingDb;

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
                || quiz.getCorrectAnswer() == null || quiz.getTitle().length() > 255
                || quiz.getContent().codePointCount(0, quiz.getContent().length()) > 20000
                || quiz.getCorrectAnswer().codePointCount(0, quiz.getCorrectAnswer().length()) > 2000) throw A704.DODREAM.authorization.AuthorizationPolicy.invalid();
        }
        if (materialId != null) {
            gradingDb.queryForList("SELECT id FROM quizzes WHERE material_id=? ORDER BY id FOR UPDATE", Long.class, materialId);
            for (Quiz quiz : quizRepository.findAllByMaterialIdOrderByQuestionNumber(materialId)) {
                if (!numbers.contains(quiz.getQuestionNumber()) && (studentQuizLogRepository.existsByQuizId(quiz.getId()) || Boolean.TRUE.equals(gradingDb.queryForObject("SELECT EXISTS(SELECT 1 FROM grading_attempt_items WHERE quiz_id=?)", Boolean.class, quiz.getId()))))
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
	 * 학생 퀴즈 풀이 기록 조회
	 */
	@Transactional(readOnly = true)
	public List<GradingResultDto> getStudentLogs(Long materialId, Long studentId) {
        policy.studentMaterial(studentId, materialId);
        Map<Long,String> attempts = new java.util.HashMap<>();
        gradingDb.query("SELECT id,attempt_id FROM grading_attempts WHERE student_id=? AND material_id=?",
            (org.springframework.jdbc.core.RowCallbackHandler) row -> attempts.put(row.getLong("id"),row.getString("attempt_id")),studentId,materialId);
		return studentQuizLogRepository.findByStudentIdAndQuizMaterialId(studentId, materialId).stream()
			.map(log -> GradingResultDto.builder()
				.attemptId(attempts.get(log.getAttemptId())).quizId(log.getQuiz().getId()).correctAnswer(log.getSnapshotCorrectAnswer())
                .snapshotAvailable(log.getAttemptId() != null).version(log.getSnapshotQuizVersion())
                .questionContent(log.getSnapshotQuestionContent()).gradingVersion(log.getGradingVersion())
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
						(existing, replacement) -> latest(existing, replacement)
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
					.submissionCount((int) materialLogs.stream().map(StudentQuizLog::getAttemptId).filter(java.util.Objects::nonNull).distinct().count())
                    .legacyLogCount((int) materialLogs.stream().filter(l -> l.getAttemptId() == null).count())
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
						(existing, replacement) -> latest(existing, replacement)
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
    static StudentQuizLog latest(StudentQuizLog a, StudentQuizLog b) {
        java.time.LocalDateTime at = a.getSubmittedAt() == null ? a.getSolvedAt() : a.getSubmittedAt();
        java.time.LocalDateTime bt = b.getSubmittedAt() == null ? b.getSolvedAt() : b.getSubmittedAt();
        if (at == null) at = java.time.LocalDateTime.MIN;
        if (bt == null) bt = java.time.LocalDateTime.MIN;
        int compare = at.compareTo(bt);
        if (compare == 0) compare = Long.compare(a.getAttemptId() == null ? 0 : a.getAttemptId(), b.getAttemptId() == null ? 0 : b.getAttemptId());
        if (compare == 0) compare = Long.compare(a.getId(), b.getId());
        return compare >= 0 ? a : b;
    }
}