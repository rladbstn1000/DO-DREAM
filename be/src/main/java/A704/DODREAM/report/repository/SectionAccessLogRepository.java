package A704.DODREAM.report.repository;

import A704.DODREAM.report.entity.SectionAccessLog;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.List;

@Repository
public interface SectionAccessLogRepository extends JpaRepository<SectionAccessLog, Long> {

    /**
     * 특정 학생의 특정 교재에 대한 모든 접근 로그 조회
     */
    List<SectionAccessLog> findByStudentIdAndMaterialId(Long studentId, Long materialId);

    /**
     * 특정 학생의 특정 교재, 챕터, 섹션에 대한 접근 로그 조회
     */
    List<SectionAccessLog> findByStudentIdAndMaterialIdAndChapterIdAndSectionIndex(
        Long studentId, Long materialId, Integer chapterId, Integer sectionIndex);

    /**
     * 특정 기간 동안의 학습 로그 조회
     */
    @Query("SELECT sal FROM SectionAccessLog sal WHERE sal.student.id = :studentId " +
           "AND sal.createdAt BETWEEN :startDate AND :endDate")
    List<SectionAccessLog> findByStudentIdAndDateRange(
        @Param("studentId") Long studentId,
        @Param("startDate") LocalDateTime startDate,
        @Param("endDate") LocalDateTime endDate);

    /**
     * 특정 교재의 챕터별 섹션 접근 횟수 통계
     */
    @Query("SELECT sal.chapterId, sal.sectionIndex, sal.sectionType, COUNT(sal) as accessCount " +
           "FROM SectionAccessLog sal WHERE sal.student.id = :studentId AND sal.material.id = :materialId " +
           "GROUP BY sal.chapterId, sal.sectionIndex, sal.sectionType " +
           "ORDER BY accessCount DESC")
    List<Object[]> countAccessByChapterAndSection(
        @Param("studentId") Long studentId,
        @Param("materialId") Long materialId);

    /**
     * 섹션 타입별 접근 통계
     */
    @Query("SELECT sal.sectionType, COUNT(sal) as accessCount, AVG(sal.durationSeconds) as avgDuration " +
           "FROM SectionAccessLog sal WHERE sal.student.id = :studentId AND sal.material.id = :materialId " +
           "GROUP BY sal.sectionType")
    List<Object[]> analyzeBySectionType(
        @Param("studentId") Long studentId,
        @Param("materialId") Long materialId);

    /**
     * 재생 모드별 통계
     */
    @Query("SELECT sal.playMode, COUNT(sal) as usageCount " +
           "FROM SectionAccessLog sal WHERE sal.student.id = :studentId " +
           "GROUP BY sal.playMode ORDER BY usageCount DESC")
    List<Object[]> analyzePlayModePreference(@Param("studentId") Long studentId);

    /**
     * 가장 많이 반복한 섹션 조회 (난이도가 높은 부분)
     */
    @Query("SELECT sal.chapterId, sal.sectionIndex, sal.sectionType, COUNT(sal) as repeatCount " +
           "FROM SectionAccessLog sal WHERE sal.student.id = :studentId AND sal.material.id = :materialId " +
           "GROUP BY sal.chapterId, sal.sectionIndex, sal.sectionType " +
           "HAVING COUNT(sal) >= :minRepeatCount " +
           "ORDER BY repeatCount DESC")
    List<Object[]> findMostRepeatedSections(
        @Param("studentId") Long studentId,
        @Param("materialId") Long materialId,
        @Param("minRepeatCount") Integer minRepeatCount);
}

