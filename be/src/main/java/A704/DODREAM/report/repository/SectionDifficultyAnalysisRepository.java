package A704.DODREAM.report.repository;

import A704.DODREAM.report.entity.SectionDifficultyAnalysis;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.LocalDate;
import java.util.List;
import java.util.Optional;

@Repository
public interface SectionDifficultyAnalysisRepository extends JpaRepository<SectionDifficultyAnalysis, Long> {

    /**
     * 특정 학생의 특정 교재에 대한 난이도 분석 결과 조회
     */
    List<SectionDifficultyAnalysis> findByStudentIdAndMaterialId(Long studentId, Long materialId);

    /**
     * 특정 학생의 특정 교재, 챕터, 섹션에 대한 최신 분석 결과 조회
     */
    @Query("SELECT sda FROM SectionDifficultyAnalysis sda " +
           "WHERE sda.student.id = :studentId AND sda.material.id = :materialId " +
           "AND sda.chapterId = :chapterId AND sda.sectionIndex = :sectionIndex " +
           "ORDER BY sda.analysisDate DESC")
    Optional<SectionDifficultyAnalysis> findLatestAnalysis(
        @Param("studentId") Long studentId,
        @Param("materialId") Long materialId,
        @Param("chapterId") Integer chapterId,
        @Param("sectionIndex") Integer sectionIndex);

    /**
     * 난이도 점수가 높은 섹션 조회 (어려워하는 부분)
     */
    @Query("SELECT sda FROM SectionDifficultyAnalysis sda " +
           "WHERE sda.student.id = :studentId AND sda.material.id = :materialId " +
           "AND sda.difficultyScore >= :minScore " +
           "ORDER BY sda.difficultyScore DESC")
    List<SectionDifficultyAnalysis> findDifficultSections(
        @Param("studentId") Long studentId,
        @Param("materialId") Long materialId,
        @Param("minScore") Double minScore);

    /**
     * 특정 날짜의 분석 결과 조회
     */
    List<SectionDifficultyAnalysis> findByStudentIdAndMaterialIdAndAnalysisDate(
        Long studentId, Long materialId, LocalDate analysisDate);

    /**
     * 섹션 타입별 평균 난이도 조회
     */
    @Query("SELECT sda.sectionType, AVG(sda.difficultyScore) as avgDifficulty " +
           "FROM SectionDifficultyAnalysis sda " +
           "WHERE sda.student.id = :studentId AND sda.material.id = :materialId " +
           "GROUP BY sda.sectionType " +
           "ORDER BY avgDifficulty DESC")
    List<Object[]> findAverageDifficultyBySectionType(
        @Param("studentId") Long studentId,
        @Param("materialId") Long materialId);
}

