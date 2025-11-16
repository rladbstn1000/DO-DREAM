package A704.DODREAM.report.service;

import A704.DODREAM.material.entity.Material;
import A704.DODREAM.material.repository.MaterialRepository;
import A704.DODREAM.user.entity.User;
import A704.DODREAM.user.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * 학습 분석 배치 작업 스케줄러
 * 정기적으로 학습 로그를 분석하여 난이도 데이터를 업데이트
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class LearningAnalysisScheduler {

    private final LearningAnalysisService learningAnalysisService;
    private final UserRepository userRepository;
    private final MaterialRepository materialRepository;

    /**
     * 매일 새벽 2시에 전체 학생의 난이도 분석 실행
     * 실제 운영 환경에서는 대량의 데이터 처리를 고려하여
     * 페이징 처리나 병렬 처리를 추가할 수 있습니다.
     */
    @Scheduled(cron = "0 0 2 * * *")
    public void scheduledDifficultyAnalysis() {
        log.info("=== 학습 난이도 분석 배치 작업 시작 ===");
        
        try {
            List<User> students = userRepository.findAll();
            int totalAnalyzed = 0;
            int totalStudents = students.size();

            for (int i = 0; i < students.size(); i++) {
                User student = students.get(i);
                
                try {
                    // 학생이 학습 중인 교재 목록 조회
                    List<Material> materials = materialRepository.findAll(); // 실제로는 학생별 교재 조회 필요
                    
                    for (Material material : materials) {
                        learningAnalysisService.performDifficultyAnalysis(
                            student.getId(), 
                            material.getId()
                        );
                        totalAnalyzed++;
                    }

                    log.info("학생 난이도 분석 완료: [{}/{}] studentId={}, 분석된 교재 수={}",
                        i + 1, totalStudents, student.getId(), materials.size());

                } catch (Exception e) {
                    log.error("학생 난이도 분석 중 오류 발생: studentId={}, error={}",
                        student.getId(), e.getMessage(), e);
                    // 한 학생의 분석 실패가 전체 배치를 중단시키지 않도록 continue
                    continue;
                }
            }

            log.info("=== 학습 난이도 분석 배치 작업 완료: 총 {}개 분석 완료 ===", totalAnalyzed);

        } catch (Exception e) {
            log.error("학습 난이도 분석 배치 작업 중 치명적 오류 발생", e);
        }
    }

    /**
     * 주간 리포트 생성 (매주 월요일 오전 9시)
     * 지난 주의 학습 패턴을 분석하여 리포트 생성
     */
    @Scheduled(cron = "0 0 9 * * MON")
    public void generateWeeklyReports() {
        log.info("=== 주간 학습 리포트 생성 시작 ===");
        
        // TODO: 주간 리포트 생성 로직 구현
        // - 지난 주 학습 시간 통계
        // - 완료한 교재/챕터 수
        // - 어려워했던 Section TOP 10
        // - 학습 개선 제안
        
        log.info("=== 주간 학습 리포트 생성 완료 ===");
    }

    /**
     * 월간 리포트 생성 (매월 1일 오전 9시)
     * 지난 달의 학습 성과를 종합 분석
     */
    @Scheduled(cron = "0 0 9 1 * *")
    public void generateMonthlyReports() {
        log.info("=== 월간 학습 리포트 생성 시작 ===");
        
        // TODO: 월간 리포트 생성 로직 구현
        // - 월간 학습 시간 통계
        // - 학습 진도율 변화
        // - 난이도별 Section 분포
        // - 학습 성취도 평가
        
        log.info("=== 월간 학습 리포트 생성 완료 ===");
    }
}

