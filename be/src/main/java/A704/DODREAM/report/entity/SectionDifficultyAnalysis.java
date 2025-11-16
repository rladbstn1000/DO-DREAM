package A704.DODREAM.report.entity;

import A704.DODREAM.global.entity.BaseTimeEntity;
import A704.DODREAM.material.entity.Material;
import A704.DODREAM.user.entity.User;
import jakarta.persistence.*;
import lombok.*;

/**
 * Section별 난이도 분석 결과를 저장하는 Entity
 * 정기적으로 로그를 분석하여 학생이 어려워하는 부분을 저장
 */
@Entity
@Table(name = "section_difficulty_analyses", indexes = {
    @Index(name = "idx_student_material_difficulty", columnList = "student_id, material_id"),
    @Index(name = "idx_difficulty_score", columnList = "difficulty_score")
})
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
public class SectionDifficultyAnalysis extends BaseTimeEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "student_id", nullable = false)
    private User student;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "material_id", nullable = false)
    private Material material;

    @Column(name = "chapter_id", nullable = false)
    private Integer chapterId;

    @Column(name = "section_index", nullable = false)
    private Integer sectionIndex;

    @Column(name = "section_type", length = 50)
    private String sectionType;

    @Column(name = "repeat_count")
    private Integer repeatCount; // 반복 재생 횟수

    @Column(name = "total_duration_seconds")
    private Integer totalDurationSeconds; // 총 재생 시간

    @Column(name = "completion_rate")
    private Double completionRate; // 완료율 (0.0 ~ 1.0)

    @Column(name = "difficulty_score")
    private Double difficultyScore; // 난이도 점수 (높을수록 어려움)

    @Column(name = "analysis_date")
    private java.time.LocalDate analysisDate; // 분석 날짜

    /**
     * 난이도 점수를 계산하는 메서드
     * 반복 횟수, 재생 시간, 완료율을 종합하여 계산
     */
    public void calculateDifficultyScore() {
        if (repeatCount == null || totalDurationSeconds == null || completionRate == null) {
            this.difficultyScore = 0.0;
            return;
        }

        // 반복 횟수가 많을수록, 재생 시간이 길수록, 완료율이 낮을수록 난이도가 높음
        double repeatWeight = 0.5;
        double durationWeight = 0.3;
        double completionWeight = 0.2;

        double normalizedRepeat = Math.min(repeatCount / 10.0, 1.0); // 10회 이상을 최대로
        double normalizedDuration = Math.min(totalDurationSeconds / 600.0, 1.0); // 10분 이상을 최대로
        double normalizedCompletion = 1.0 - completionRate; // 완료율이 낮을수록 높은 점수

        this.difficultyScore = (normalizedRepeat * repeatWeight) +
                              (normalizedDuration * durationWeight) +
                              (normalizedCompletion * completionWeight);
    }
}

