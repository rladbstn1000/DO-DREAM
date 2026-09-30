package A704.DODREAM.file.controller;

import A704.DODREAM.auth.dto.request.UserPrincipal;
import A704.DODREAM.authorization.AuthorizationPolicy;
import A704.DODREAM.file.dto.*;
import A704.DODREAM.file.repository.UploadedFileRepository;
import A704.DODREAM.file.service.CloudFrontService;
import A704.DODREAM.file.service.S3Service;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import java.util.List;

@RestController
@RequestMapping("/api/files")
@RequiredArgsConstructor
public class FileUploadController {
    private final AuthorizationPolicy policy;
    private final UploadedFileRepository files;
    private final S3Service storage;
    private final CloudFrontService signer;
    @PostMapping("/presigned-url")
    public ResponseEntity<PresignedUrlResponse> upload(@AuthenticationPrincipal UserPrincipal actor,
            @RequestBody PresignedUrlRequest request) {
        policy.teacher(actor.userId());
        A704.DODREAM.file.service.PdfInputPolicy.filename(request.getFileName());
        if (!"application/pdf".equals(request.getContentType())) throw AuthorizationPolicy.invalid();
        return ResponseEntity.ok(storage.generatePresignedUrl(request, actor.userId()));
    }
    @GetMapping("/{fileId}/download-url")
    public ResponseEntity<DownloadUrlResponse> download(@AuthenticationPrincipal UserPrincipal actor,
            @PathVariable Long fileId) {
        var file = policy.ownedFile(actor.userId(), fileId);
        if (file.getS3Key() == null) throw AuthorizationPolicy.hidden();
        return ResponseEntity.ok(DownloadUrlResponse.builder().fileId(fileId)
            .fileName(file.getOriginalFileName()).downloadUrl(signer.generateSignedUrl(file.getS3Key()))
            .expiresIn(3600L).build());
    }
    @GetMapping
    public ResponseEntity<List<FileUploadResponse>> list(@AuthenticationPrincipal UserPrincipal actor) {
        policy.teacher(actor.userId());
        return ResponseEntity.ok(files.findByUploaderId(actor.userId()).stream().filter(file -> {
            try { policy.ownedFile(actor.userId(), file.getId()); return true; }
            catch (A704.DODREAM.authorization.AuthorizationFailure denied) { return false; }
        }).map(file -> FileUploadResponse.builder().fileId(file.getId()).originalFileName(file.getOriginalFileName())
            .fileSize(file.getFileSize()).ocrStatus(file.getOcrStatus()).uploadedAt(file.getCreatedAt()).build()).toList());
    }
}
