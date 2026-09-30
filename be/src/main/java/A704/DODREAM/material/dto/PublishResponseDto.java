package A704.DODREAM.material.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PublishResponseDto {
    private Boolean success;
    private Long pdfId;
    private Long materialId;
    private String filename;
    private String jsonS3Key;
    private LocalDateTime publishedAt;
    private String message;
    private A704.DODREAM.indexing.IndexingSummary indexing;
}
