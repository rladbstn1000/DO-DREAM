package A704.DODREAM.material.controller;

import A704.DODREAM.material.dto.MaterialShareRequest;
import A704.DODREAM.material.dto.MaterialShareResponse;
import A704.DODREAM.material.service.MaterialShareService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Slf4j
@RestController
@RequestMapping("/api/materials")
@RequiredArgsConstructor
public class MaterialShareController {

    private final MaterialShareService materialShareService;

    @PostMapping("/share")
    public ResponseEntity<MaterialShareResponse> shareMaterial(
            @RequestBody MaterialShareRequest request){
        MaterialShareResponse response = materialShareService.shareMaterial(request);
        return ResponseEntity.ok(response);
    }


}
