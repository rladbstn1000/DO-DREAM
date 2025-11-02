package A704.DODREAM.material.controller;

import A704.DODREAM.material.dto.MaterialShareRequest;
import A704.DODREAM.material.dto.MaterialShareResponse;
import A704.DODREAM.material.service.MaterialShareService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Tag(name = "Material Share", description = "학습자료 공유 API")
@Slf4j
@RestController
@RequestMapping("/api/materials")
@RequiredArgsConstructor
public class MaterialShareController {

    private final MaterialShareService materialShareService;

    @Operation(
            summary = "학습 자료 공유 + 푸시 알림",
            description = "선생님이 학생들에게 학습 자료를 공유하면 학생의 등록된 디바이스로 푸시 알림이 전송됩니다."
    )
    @PostMapping("/share")
    public ResponseEntity<MaterialShareResponse> shareMaterial(
            @RequestBody MaterialShareRequest request){
        MaterialShareResponse response = materialShareService.shareMaterial(request);
        return ResponseEntity.ok(response);
    }


}
