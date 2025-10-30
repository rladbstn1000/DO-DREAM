package A704.DODREAM.fcm.controller;

import A704.DODREAM.fcm.dto.FcmSendDto;
import A704.DODREAM.fcm.dto.FcmResponseDto;
import A704.DODREAM.fcm.service.FcmService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/fcm")
public class FcmController {
    private final FcmService fcmService;

    @PostMapping("/send")
    public ResponseEntity<FcmResponseDto> pushMessage(
            @RequestBody FcmSendDto fcmSendDto) {

        FcmResponseDto response = fcmService.sendMessageTo(fcmSendDto);  // ← 수정!
        return ResponseEntity.ok(response);
    }
}