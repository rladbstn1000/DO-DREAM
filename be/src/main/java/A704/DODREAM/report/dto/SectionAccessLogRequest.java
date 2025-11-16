package A704.DODREAM.report.dto;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * 학생이 Section을 재생/접근할 때마다 기록하는 로그 요청 DTO
 */
@Getter
@NoArgsConstructor
@AllArgsConstructor
public class SectionAccessLogRequest {
    
    private Long materialId;
    private Integer chapterId;
    private Integer sectionIndex;
    private String sectionType; // paragraph, heading, formula, image_description
    private String playMode; // single, continuous, repeat
    private Integer durationSeconds; // 실제 재생된 시간 (초)
    private Boolean completed; // 섹션을 끝까지 들었는지 여부
}

