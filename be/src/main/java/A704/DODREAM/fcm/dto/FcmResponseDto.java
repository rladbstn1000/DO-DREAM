package A704.DODREAM.fcm.dto;

import lombok.*;

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class FcmResponseDto {
    private boolean success;
    private String message;
    private FcmResult result;

    @Getter
    @Setter
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class FcmResult {
        private String messageId;      // FCM 메시지 ID
        private Integer statusCode;     // HTTP 상태 코드
        private String errorCode;       // 에러 코드 (실패 시)
        private String errorMessage;    // 에러 메시지 (실패 시)
    }
}
