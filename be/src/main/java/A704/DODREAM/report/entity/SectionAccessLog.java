package A704.DODREAM.report.entity;

import A704.DODREAM.global.entity.BaseTimeEntity;
import A704.DODREAM.material.entity.Material;
import A704.DODREAM.user.entity.User;
import jakarta.persistence.*;
import lombok.*;

/**
 * 학생의 Section 접근 로그를 저장하는 Entity
 * TTS로 학습할 때 각 Section별 재생 기록을 추적
 */
@Entity
@Table(name = "section_access_logs", indexes = {
    @Index(name = "idx_student_material", columnList = "student_id, material_id"),
    @Index(name = "idx_chapter_section", columnList = "chapter_id, section_index"),
    @Index(name = "idx_created_at", columnList = "created_at")
})
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
public class SectionAccessLog extends BaseTimeEntity {

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
    private String sectionType; // paragraph, heading, formula, image_description

    @Column(name = "play_mode", length = 20)
    private String playMode; // single, continuous, repeat

    @Column(name = "duration_seconds")
    private Integer durationSeconds; // 실제 재생된 시간

    @Column(name = "completed")
    @Builder.Default
    private Boolean completed = false; // 섹션을 끝까지 들었는지 여부
}

