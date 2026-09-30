package A704.DODREAM.file.service;

import java.time.Duration;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import A704.DODREAM.file.dto.PresignedUrlRequest;
import A704.DODREAM.file.dto.PresignedUrlResponse;
import A704.DODREAM.file.entity.OcrStatus;
import A704.DODREAM.file.entity.UploadedFile;
import A704.DODREAM.file.repository.UploadedFileRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.PresignedPutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.model.PutObjectPresignRequest;

@Slf4j
@Service
@RequiredArgsConstructor
public class S3Service {

	private final S3Presigner s3Presigner;
	private final UploadedFileRepository uploadedFileRepository;

	@Value("${aws.s3.bucket}")
	private String bucketName;

	@Value("${aws.s3.upload-prefix}")
	private String uploadPrefix;

	@Value("${aws.s3.presign-exp-minutes}")
	private long presignExpMinutes;

	@Transactional
	public PresignedUrlResponse generatePresignedUrl(PresignedUrlRequest request, Long userId) {
		PdfInputPolicy.filename(request.getFileName());
        if (!"application/pdf".equals(request.getContentType()) || request.getFileSize() == null
            || request.getFileSize() <= 0 || request.getFileSize() > PdfInputPolicy.MAX_BYTES) {
            throw new org.springframework.web.server.ResponseStatusException(org.springframework.http.HttpStatus.BAD_REQUEST,"INVALID_FILE_SIZE");
        }
        // Generate unique S3 key
		String s3Key = generateS3Key(request.getFileName());

		// Create file record in DB with PENDING status
		UploadedFile uploadedFile = UploadedFile.builder()
			.originalFileName(request.getFileName())
			.s3Key(s3Key)
			.s3Bucket(bucketName)
			.contentType(request.getContentType())
            .fileSize(request.getFileSize())
			.ocrStatus(OcrStatus.PENDING)
			.uploaderId(userId)
			.build();

		UploadedFile savedFile = uploadedFileRepository.save(uploadedFile);

		// Generate presigned URL
		PutObjectRequest putObjectRequest = PutObjectRequest.builder()
			.bucket(bucketName)
			.key(s3Key)
			.contentType(request.getContentType())
            .contentLength(request.getFileSize())
			// contentDisposition은 PUT 요청에 불필요하며, 서명 불일치의 원인이 됨
			// 다운로드 시 필요하면 GetObjectRequest에서 설정
			.build();

		PutObjectPresignRequest presignRequest = PutObjectPresignRequest.builder()
			.signatureDuration(Duration.ofMinutes(presignExpMinutes))
			.putObjectRequest(putObjectRequest)
			.build();

		PresignedPutObjectRequest presignedRequest = s3Presigner.presignPutObject(presignRequest);

		log.info("Generated bounded upload URL fileId={}", savedFile.getId());

		return PresignedUrlResponse.builder()
			.presignedUrl(presignedRequest.url().toString())
			.s3Key(s3Key)
			.fileId(savedFile.getId().toString())
			.expiresIn(presignExpMinutes * 60)
			.build();
	}

	private String generateS3Key(String originalFileName) {
		String uuid = UUID.randomUUID().toString();
		String extension = "";

		int lastDotIndex = originalFileName.lastIndexOf('.');
		if (lastDotIndex > 0) {
			extension = originalFileName.substring(lastDotIndex);
		}

		return uploadPrefix + "/" + uuid + extension;
	}
}