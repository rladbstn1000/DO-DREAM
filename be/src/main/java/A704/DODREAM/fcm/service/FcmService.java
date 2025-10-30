package A704.DODREAM.fcm.service;

import A704.DODREAM.fcm.dto.FcmResponseDto;
import A704.DODREAM.fcm.dto.FcmSendDto;
import com.google.auth.oauth2.GoogleCredentials;
import com.google.firebase.FirebaseApp;
import com.google.firebase.FirebaseOptions;
import com.google.firebase.messaging.FirebaseMessaging;
import com.google.firebase.messaging.FirebaseMessagingException;
import com.google.firebase.messaging.Message;
import com.google.firebase.messaging.Notification;
import jakarta.annotation.PostConstruct;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;

import java.io.IOException;

@Slf4j
@Service
public class FcmService {

    @PostConstruct
    public void initialize() {
        try {
            if (FirebaseApp.getApps().isEmpty()) {
                ClassPathResource resource = new ClassPathResource("firebase/dodream-25978-firebase-adminsdk-fbsvc-b587126b76.json");

                FirebaseOptions options = FirebaseOptions.builder()
                        .setCredentials(GoogleCredentials.fromStream(resource.getInputStream()))
                        .build();

                FirebaseApp.initializeApp(options);
            }
        } catch (IOException e) {
            throw new RuntimeException("Firebase 초기화 실패", e);
        }
    }

    public FcmResponseDto sendMessageTo(FcmSendDto fcmSendDto) {
        try {
            Message message = Message.builder()
                    .setToken(fcmSendDto.getToken())
                    .setNotification(Notification.builder()
                            .setTitle(fcmSendDto.getTitle())
                            .setBody(fcmSendDto.getBody())
                            .build())
                    .build();

            String response = FirebaseMessaging.getInstance().send(message);

            log.info("FCM 메시지 전송 성공: {}", response);

            return FcmResponseDto.builder()
                    .success(true)
                    .message("푸시 알림 전송 완료")
                    .result(FcmResponseDto.FcmResult.builder()
                            .messageId(response)
                            .statusCode(200)
                            .build())
                    .build();

        } catch (FirebaseMessagingException e) {
            log.error("FCM 메시지 전송 실패: {}", e.getMessage(), e);

            return FcmResponseDto.builder()
                    .success(false)
                    .message("푸시 알림 전송 실패: " + e.getMessage())
                    .result(FcmResponseDto.FcmResult.builder()
                            .statusCode(500)
                            .errorCode(e.getMessagingErrorCode() != null ?
                                    e.getMessagingErrorCode().name() : "UNKNOWN")  // ← 수정!
                            .errorMessage(e.getMessage())
                            .build())
                    .build();
        }
    }
}