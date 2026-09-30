package A704.DODREAM.file.service;

import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.security.KeyFactory;
import java.security.PrivateKey;
import java.security.Signature;
import java.security.spec.PKCS8EncodedKeySpec;
import java.time.Instant;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.reactive.function.client.WebClient;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import A704.DODREAM.file.entity.OcrStatus;
import A704.DODREAM.file.entity.UploadedFile;
import A704.DODREAM.file.repository.UploadedFileRepository;
import lombok.extern.slf4j.Slf4j;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.S3Exception;

@Service
@Slf4j
public class PdfService {
    @Autowired private A704.DODREAM.authorization.AuthorizationPolicy policy;
    @Autowired private A704.DODREAM.indexing.IndexingService indexingService;
    @Autowired private A704.DODREAM.indexing.IndexingStore indexingStore;
    @Autowired private A704.DODREAM.indexing.IndexingLocalHooks indexingHooks;
    @Autowired private org.springframework.core.env.Environment environment;

	@Autowired
	private UploadedFileRepository uploadedFileRepository;

	@Autowired
	private CloudFrontService cloudFrontService;

	@Autowired
	private WebClient webClient;

	@Autowired
	private S3Client s3Client;  // AWS SDK v2

	@Value("${fastapi.url}")
	private String fastApiUrl;

	@Value("${aws.s3.bucket}")
	private String bucketName;

	@Value("${aws.cloudfront.domain}")
	private String cloudFrontDomain;

	@Value("${aws.cloudfront.key-pair-id}")
	private String keyPairId;

	@Value("${aws.cloudfront.private-key-pem}")
	private String privateKeyPath;

	@Autowired
	private ObjectMapper objectMapper;  // JSON 직렬화용

	@Value("${aws.s3.upload-prefix:pdfs}")
	private String uploadPrefix;

	/**
	 * PDF 업로드 + 파싱 통합 API (바이너리 스트림 방식)
	 *
	 * @param pdfBytes: PDF 바이너리 데이터
	 * @param filename: 원본 파일명
	 * @param userId:   사용자 ID
	 * @return 파싱된 결과 및 메타데이터
	 */
	public Map<String, Object> uploadAndParsePdfFromBytes(byte[] pdfBytes, String filename, Long userId,
		String authorizationHeader) {
        indexingStore.teacher(userId);
		try {
			// 1. 파일 검증
            PdfInputPolicy.filename(filename);
            PdfInputPolicy.content(pdfBytes);

			// 2. S3 키 생성
            String s3Key=environment.acceptsProfiles(org.springframework.core.env.Profiles.of("local"))
                && filename.matches("indexing-synthetic(?:-[0-9a-f-]{36})?\\.pdf")
                ? "local/synthetic/indexing-pdf/"+UUID.randomUUID()+".pdf" : generateS3Key(filename);

			// 3. S3에 업로드 (한글 파일명 URL 인코딩 처리)
			String encodedFilename = URLEncoder.encode(filename, StandardCharsets.UTF_8);

			PutObjectRequest putRequest = PutObjectRequest.builder()
				.bucket(bucketName)
				.key(s3Key)
				.contentType("application/pdf")
				.metadata(Map.of("original-filename", encodedFilename, "uploaded-by", userId.toString(), "uploaded-at",
					LocalDateTime.now().toString()))
				.build();

            indexingHooks.boundary(0,false);
			s3Client.putObject(putRequest, RequestBody.fromBytes(pdfBytes));

			log.info("✅ PDF S3 업로드 완료: {}", s3Key);

			// 4. DB에 UploadedFile 레코드 생성
			UploadedFile uploadedFile = UploadedFile.builder()
				.originalFileName(filename)
				.s3Key(s3Key)
				.s3Bucket(bucketName)
				.contentType("application/pdf")
				.fileSize((long)pdfBytes.length)
				.ocrStatus(OcrStatus.PENDING)
				.uploaderId(userId)
				.build();

            long savedFileId=indexingStore.createUploadedFile(userId,uploadedFile);

			log.info("✅ DB 저장 완료: pdfId={}", savedFileId);

			// 5. CloudFront signed URL 생성
			String cloudFrontUrl = cloudFrontService.generateSignedUrl(s3Key);

			// 6. FastAPI 호출하여 파싱
			String fastApiEndpoint = fastApiUrl + "/document/parse-pdf-from-cloudfront";

			Map<String, Object> request = new HashMap<>();
			request.put("cloudfront_url", cloudFrontUrl);
            request.put("uploaded_file_id", savedFileId);

            indexingHooks.boundary(savedFileId,filename.startsWith("indexing-synthetic"));
			ResponseEntity<Map> response = webClient.post()
				.uri(fastApiEndpoint)
                .header("Authorization", authorizationHeader)
				.bodyValue(request)
				.retrieve()
				.onStatus(status -> status.is4xxClientError() || status.is5xxServerError(),
					clientResponse -> clientResponse.bodyToMono(String.class)
						.map(errorBody -> new RuntimeException("PDF provider request failed")))
				.toEntity(Map.class)
				.block(java.time.Duration.ofSeconds(15));

			if (response.getBody() == null) {
				throw new RuntimeException("FastAPI 응답이 비어있습니다.");
			}

			Map<String, Object> parsedData = (Map<String, Object>)response.getBody().get("parsed_data");

			if (parsedData == null) {
				throw new RuntimeException("FastAPI 응답에 parsed_data가 없습니다.");
			}

            // Parsed object preparation is outside the publication transaction. The JSON reference
            // and durable initial-index job become visible together; no user token enters the queue.
            var indexing=indexingService.completeInitial(userId,savedFileId,parsedData);
            return Map.of("pdfId",savedFileId,"filename",filename,"parsedData",parsedData,"indexing",indexing);

		} catch (A704.DODREAM.authorization.AuthorizationFailure | org.springframework.web.server.ResponseStatusException | A704.DODREAM.indexing.IndexingFailure denied) {
            throw denied;
        } catch (Exception e) {
			throw new RuntimeException("PDF 업로드 및 파싱 실패: " + e.getMessage());
		}
	}

	/**
	 * PDF 업로드 + 파싱 통합 API (MultipartFile 방식)
	 *
	 * @param file:   업로드할 PDF 파일
	 * @param userId: 사용자 ID
	 * @return 파싱된 결과 및 메타데이터
	 */
	@Transactional
	public Map<String, Object> uploadAndParsePdf(MultipartFile file, Long userId) {
		try {
			// 1. 파일 검증
			if (file.isEmpty()) {
				throw new RuntimeException("파일이 비어있습니다.");
			}

			String originalFilename = file.getOriginalFilename();
			if (originalFilename == null || !originalFilename.toLowerCase().endsWith(".pdf")) {
				throw new RuntimeException("PDF 파일만 업로드 가능합니다.");
			}

			// 2. S3 키 생성
			String s3Key = generateS3Key(originalFilename);

			// 3. S3에 업로드 (한글 파일명 URL 인코딩 처리)
			String encodedFilename = URLEncoder.encode(originalFilename, StandardCharsets.UTF_8);

			PutObjectRequest putRequest = PutObjectRequest.builder()
				.bucket(bucketName)
				.key(s3Key)
				.contentType("application/pdf")
				.metadata(Map.of("original-filename", encodedFilename, "uploaded-by", userId.toString(), "uploaded-at",
					LocalDateTime.now().toString()))
				.build();

			s3Client.putObject(putRequest, RequestBody.fromInputStream(file.getInputStream(), file.getSize()));

			log.info("✅ PDF S3 업로드 완료: {}", s3Key);

			// 4. DB에 UploadedFile 레코드 생성
			UploadedFile uploadedFile = UploadedFile.builder()
				.originalFileName(originalFilename)
				.s3Key(s3Key)
				.s3Bucket(bucketName)
				.contentType("application/pdf")
				.fileSize(file.getSize())
				.ocrStatus(OcrStatus.PENDING)
				.uploaderId(userId)
				.build();

			UploadedFile savedFile = uploadedFileRepository.save(uploadedFile);

			log.info("✅ DB 저장 완료: pdfId={}", savedFile.getId());

			// 5. CloudFront signed URL 생성
			String cloudFrontUrl = cloudFrontService.generateSignedUrl(s3Key);

			// 6. FastAPI 호출하여 파싱
			String fastApiEndpoint = fastApiUrl + "/document/parse-pdf-from-cloudfront";

			Map<String, String> request = new HashMap<>();
			request.put("cloudfront_url", cloudFrontUrl);

			ResponseEntity<Map> response = webClient.post()
				.uri(fastApiEndpoint)
				.bodyValue(request)
				.retrieve()
				.onStatus(status -> status.is4xxClientError() || status.is5xxServerError(),
					clientResponse -> clientResponse.bodyToMono(String.class)
						.map(errorBody -> new RuntimeException("FastAPI 에러: " + errorBody)))
				.toEntity(Map.class)
				.block();

			if (response.getBody() == null) {
				throw new RuntimeException("FastAPI 응답이 비어있습니다.");
			}

			Map<String, Object> parsedData = (Map<String, Object>)response.getBody().get("parsed_data");

			if (parsedData == null) {
				throw new RuntimeException("FastAPI 응답에 parsed_data가 없습니다.");
			}

			// 7. JSON을 S3에 저장
			String jsonS3Key = uploadJsonToS3(s3Key, parsedData, userId.toString());

			// 8. DB 업데이트 (파싱 결과 반영)
			savedFile.setJsonS3Key(jsonS3Key);
			savedFile.setParsedAt(LocalDateTime.now());

			// 필수 필드만 DB에 저장 (검색용)
			if (parsedData.containsKey("indexes")) {
				List<String> indexes = (List<String>)parsedData.get("indexes");
				savedFile.setIndexes(String.join(",", indexes));
			}

			uploadedFileRepository.save(savedFile);

			log.info("✅ 전체 프로세스 완료: pdfId={}", savedFile.getId());

			return Map.of("pdfId", savedFile.getId(), "filename", originalFilename, "s3Key", s3Key, "jsonS3Key",
				jsonS3Key, "parsedData", parsedData);

		} catch (IOException e) {
			throw new RuntimeException("파일 업로드 실패: " + e.getMessage());
		} catch (A704.DODREAM.authorization.AuthorizationFailure | org.springframework.web.server.ResponseStatusException denied) {
            throw denied;
        } catch (Exception e) {
			throw new RuntimeException("PDF 업로드 및 파싱 실패: " + e.getMessage());
		}
	}

	/**
	 * S3 키 생성 (UUID 기반)
	 */
	private String generateS3Key(String originalFileName) {
		String uuid = UUID.randomUUID().toString();
		String extension = ".pdf";

		int lastDotIndex = originalFileName.lastIndexOf('.');
		if (lastDotIndex > 0) {
			extension = originalFileName.substring(lastDotIndex);
		}

		return uploadPrefix + "/" + uuid + extension;
	}

	/**
	 * PDF 파싱 및 JSON S3 저장 (기존 방식 - presigned URL 사용)
	 */
	@Transactional
	public Map<String, Object> parsePdfAndSave(Long pdfId, Long userId) {
		// 1. DB에서 PDF 정보 조회
		UploadedFile uploadedFile = uploadedFileRepository.findById(pdfId)
			.orElseThrow(() -> new RuntimeException("PDF not found"));

		// 2. 권한 검증
		if (!uploadedFile.getUploaderId().equals(userId)) {
			throw new RuntimeException("Not your PDF");
		}

		// 3. S3 키 확인
		if (uploadedFile.getS3Key() == null) {
			throw new RuntimeException("S3 key not found. Please upload via presigned URL first.");
		}

		// 4. CloudFront signed URL 생성
		//    String cloudFrontUrl = generateCloudFrontSignedUrl(uploadedFile.getS3Key());

		String cloudFrontUrl = cloudFrontService.generateSignedUrl(uploadedFile.getS3Key());
		// 5. FastAPI 호출
		String fastApiEndpoint = fastApiUrl + "/document/parse-pdf-from-cloudfront";

		Map<String, String> request = new HashMap<>();
		request.put("cloudfront_url", cloudFrontUrl);

		try {
			ResponseEntity<Map> response = webClient.post()
				.uri(fastApiEndpoint)
				.bodyValue(request)
				.retrieve()
				.onStatus(status -> status.is4xxClientError() || status.is5xxServerError(),
					clientResponse -> clientResponse.bodyToMono(String.class)
						.map(errorBody -> new RuntimeException("FastAPI 에러: " + errorBody)))
				.toEntity(Map.class)
				.block();

			if (response.getBody() == null) {
				throw new RuntimeException("FastAPI 응답이 비어있습니다.");
			}

			Map<String, Object> parsedData = (Map<String, Object>)response.getBody().get("parsed_data");

			if (parsedData == null) {
				throw new RuntimeException("FastAPI 응답에 parsed_data가 없습니다.");
			}

			// ===== 6. JSON을 S3에 저장 =====
			String jsonS3Key = uploadJsonToS3(uploadedFile.getS3Key(), parsedData, userId.toString());

			// ===== 7. DB 업데이트 (메타데이터 + 필수 필드만) =====
			uploadedFile.setJsonS3Key(jsonS3Key);  // S3에 저장된 JSON 경로
			uploadedFile.setParsedAt(LocalDateTime.now());

			// 필수 필드만 DB에 저장 (검색용)
			if (parsedData.containsKey("indexes")) {
				List<String> indexes = (List<String>)parsedData.get("indexes");
				uploadedFile.setIndexes(String.join(",", indexes));  // 목차만 DB에
			}

			uploadedFileRepository.save(uploadedFile);

			return Map.of("pdfId", pdfId, "filename", uploadedFile.getOriginalFileName(), "jsonS3Key", jsonS3Key,
				// 프론트에 S3 경로 알려줌
				"parsedData", parsedData  // 즉시 사용할 수 있게 전체 JSON도 반환
			);

		} catch (A704.DODREAM.authorization.AuthorizationFailure | org.springframework.web.server.ResponseStatusException denied) {
            throw denied;
        } catch (Exception e) {
			throw new RuntimeException("PDF 파싱 실패: " + e.getMessage());
		}
	}

	/**
	 * JSON을 S3에 업로드
	 *
	 * @param pdfS3Key: 원본 PDF의 S3 키 (예: pdfs/user123/2024/01/abc123.pdf)
	 * @param jsonData: 파싱된 JSON 데이터
	 * @param username: 사용자 ID
	 * @return S3에 저장된 JSON의 키
	 */
	private String uploadJsonToS3(String pdfS3Key, Map<String, Object> jsonData, String username) {
		try {
			// PDF 경로에서 파일명 추출
			// pdfs/user123/2024/01/abc123.pdf → abc123
			String filename = pdfS3Key.substring(pdfS3Key.lastIndexOf("/") + 1).replace(".pdf", "");

			// JSON S3 키 생성 (같은 구조로)
			// parsed-json/user123/2024/01/abc123.json
			String jsonS3Key = pdfS3Key.replace(uploadPrefix + "/", "parsed-json/").replace(".pdf", ".json");

			// JSON을 예쁘게 포맷팅
			String jsonString = objectMapper.writerWithDefaultPrettyPrinter().writeValueAsString(jsonData);
			String encodedUsername = URLEncoder.encode(username, StandardCharsets.UTF_8);

			// S3에 업로드
			PutObjectRequest putRequest = PutObjectRequest.builder()
				.bucket(bucketName)
				.key(jsonS3Key)
				.contentType("application/json")
				.metadata(Map.of("original-pdf", pdfS3Key, "parsed-at", LocalDateTime.now().toString(), "owner",
					encodedUsername))
				.build();

			s3Client.putObject(putRequest, RequestBody.fromString(jsonString));

			System.out.println("✅ JSON S3 저장 완료: " + jsonS3Key);

			return jsonS3Key;

		} catch (JsonProcessingException e) {
			throw new RuntimeException("JSON 직렬화 실패: " + e.getMessage());
		} catch (S3Exception e) {
			throw new RuntimeException("S3 업로드 실패: " + e.getMessage());
		}
	}

	/**
	 * S3에서 JSON 다운로드 (나중에 재조회할 때)
	 */
	public Map<String, Object> getJsonFromS3(Long pdfId, Long userId) {
        policy.ownedFile(userId, pdfId);
		UploadedFile uploadedFile = uploadedFileRepository.findById(pdfId)
			.orElseThrow(() -> new RuntimeException("PDF not found"));

		// 권한 검증
		if (!uploadedFile.getUploaderId().equals(userId)) {
			throw new RuntimeException("Not your PDF");
		}

		if (uploadedFile.getJsonS3Key() == null) {
			throw new RuntimeException("파싱된 JSON이 없습니다.");
		}

		try {
			// S3에서 JSON 다운로드
			GetObjectRequest getRequest = GetObjectRequest.builder()
				.bucket(bucketName)
				.key(uploadedFile.getJsonS3Key())
				.build();

			ResponseInputStream<GetObjectResponse> response = s3Client.getObject(getRequest);
			String jsonString = A704.DODREAM.file.service.ObjectJsonReader.read(response);

			// JSON 파싱
			Map<String, Object> jsonData = objectMapper.readValue(jsonString, Map.class);

			return Map.of("pdfId", pdfId, "filename", uploadedFile.getOriginalFileName(), "parsedAt",
				uploadedFile.getParsedAt(), "parsedData", jsonData);

		} catch (A704.DODREAM.authorization.AuthorizationFailure | org.springframework.web.server.ResponseStatusException denied) {
            throw denied;
        } catch (Exception e) {
			throw new RuntimeException("JSON 조회 실패: " + e.getMessage());
		}
	}

	/**
	 * CloudFront Signed URL 생성 (FastAPI 파싱용 - GET 권한)
	 * <p>
	 * 이건 S3 presigned URL과 다름!
	 * S3 presigned URL: 업로드용 (PUT)
	 * CloudFront signed URL: 다운로드/파싱용 (GET)
	 */
	private String generateCloudFrontSignedUrl(String s3Key) {
		try {
			// 1. CloudFront URL 생성
			String resourceUrl = "https://" + cloudFrontDomain + "/" + s3Key;

			// 2. 만료 시간 (Unix timestamp - 초 단위)
			long expiresEpochSeconds = Instant.now().plusSeconds(3600).getEpochSecond();

			// 3. Canned Policy JSON 생성
			String policy = createCannedPolicy(resourceUrl, expiresEpochSeconds);

			// 4. Private key 로드
			PrivateKey privateKey = loadPrivateKey(privateKeyPath);

			// 5. Policy 서명 생성
			String signature = signPolicy(policy, privateKey);

			// 6. URL 인코딩된 signature
			String encodedSignature = makeBytesUrlSafe(signature);

			// 7. Signed URL 조합
			String signedUrl =
				resourceUrl + "?Expires=" + expiresEpochSeconds + "&Signature=" + encodedSignature + "&Key-Pair-Id="
					+ keyPairId;

			log.info("✅ CloudFront signed URL 생성 완료: {}", s3Key);
			return signedUrl;

		} catch (A704.DODREAM.authorization.AuthorizationFailure | org.springframework.web.server.ResponseStatusException denied) {
            throw denied;
        } catch (Exception e) {
			log.error("❌ CloudFront signed URL 생성 실패: {}", e.getClass().getSimpleName());
			throw new RuntimeException("CloudFront signed URL 생성 실패: " + e.getMessage());
		}
	}

	private String createCannedPolicy(String resourceUrl, long expiresEpochSeconds) {
		return String.format(
			"{\"Statement\":[{\"Resource\":\"%s\",\"Condition\":{\"DateLessThan\":{\"AWS:EpochTime\":%d}}}]}",
			resourceUrl, expiresEpochSeconds);
	}

	private String signPolicy(String policy, PrivateKey privateKey) throws Exception {
		// SHA1withRSA 서명 생성
		Signature signature = Signature.getInstance("SHA1withRSA");
		signature.initSign(privateKey);
		signature.update(policy.getBytes(StandardCharsets.UTF_8));

		byte[] signatureBytes = signature.sign();

		// Base64 인코딩
		return Base64.getEncoder().encodeToString(signatureBytes);
	}

	private String makeBytesUrlSafe(String base64String) {
		return base64String.replace("+", "-").replace("=", "_").replace("/", "~");
	}

	/**
	 * JSON 파일의 CloudFront Signed URL 생성 (프론트엔드 다운로드용)
	 *
	 * @param pdfId:  PDF ID
	 * @param userId: 사용자 ID (권한 검증용)
	 * @return CloudFront signed URL
	 */
	public String generateJsonSignedUrl(Long pdfId, Long userId) {
        policy.ownedFile(userId, pdfId);
		// 1. DB에서 PDF 조회
		UploadedFile uploadedFile = uploadedFileRepository.findById(pdfId)
			.orElseThrow(() -> new RuntimeException("PDF not found"));

		// 2. 권한 검증
		if (!uploadedFile.getUploaderId().equals(userId)) {
			throw new RuntimeException("Not your PDF");
		}

		// 3. JSON S3 키 확인
		if (uploadedFile.getJsonS3Key() == null || uploadedFile.getJsonS3Key().isEmpty()) {
			throw new RuntimeException("파싱된 JSON이 없습니다. 먼저 PDF를 파싱해주세요.");
		}

		// 4. CloudFront signed URL 생성
		String signedUrl = cloudFrontService.generateSignedUrl(uploadedFile.getJsonS3Key());

		log.info("✅ JSON 다운로드 URL 생성 완료: pdfId={}, userId={}", pdfId, userId);

		return signedUrl;
	}

	/**
	 * Private key 로드 (CloudFront용)
	 * 파일 경로 또는 PEM 내용 자체를 받을 수 있음
	 */
	private PrivateKey loadPrivateKey(String privateKeyInput) throws Exception {
		String privateKeyPEM;

		// PEM 헤더가 있으면 직접 PEM 내용으로 간주
		if (privateKeyInput.contains("-----BEGIN PRIVATE KEY-----")) {
			privateKeyPEM = privateKeyInput;
		} else {
			// 파일 경로로 간주
			byte[] keyBytes = Files.readAllBytes(Paths.get(privateKeyInput));
			privateKeyPEM = new String(keyBytes);
		}

		// PEM 포맷 정리
		String cleanedKey = privateKeyPEM.replace("-----BEGIN PRIVATE KEY-----", "")
			.replace("-----END PRIVATE KEY-----", "")
			.replaceAll("\\s", "");

		byte[] decoded = Base64.getDecoder().decode(cleanedKey);
		PKCS8EncodedKeySpec spec = new PKCS8EncodedKeySpec(decoded);
		KeyFactory kf = KeyFactory.getInstance("RSA");
		return kf.generatePrivate(spec);
	}

	/**
	 * 개념 Check 추출 API
	 * S3에 저장된 JSON에서 s_title == "개념 Check"인 항목만 필터링하여
	 * FastAPI로 전송 후 가공된 결과를 S3에 저장
	 *
	 * @param pdfId: PDF ID
	 * @param userId: 사용자 ID (권한 검증용)
	 * @return 가공된 개념 Check 데이터
	 */
	/**
	 * 개념 Check 필터링만 수행 (GET - FastAPI 호출 없이 빠르게 반환)
	 */
	@Transactional(readOnly = true)
	public Map<String, Object> getConceptCheckOnly(Long pdfId, Long userId) {
        policy.ownedFile(userId, pdfId);
		try {
			// 1. DB에서 PDF 정보 조회
			UploadedFile uploadedFile = uploadedFileRepository.findById(pdfId)
				.orElseThrow(() -> new RuntimeException("PDF를 찾을 수 없습니다."));

			// 2. 권한 검증
			if (!uploadedFile.getUploaderId().equals(userId)) {
				throw new RuntimeException("권한이 없습니다.");
			}

			// 3. JSON S3 키 확인 (파싱된 JSON이 있어야 함)
			if (uploadedFile.getJsonS3Key() == null || uploadedFile.getJsonS3Key().isEmpty()) {
				throw new RuntimeException("파싱된 JSON이 없습니다. 먼저 PDF를 파싱해주세요.");
			}

			// 4. S3에서 JSON 다운로드
			GetObjectRequest getRequest = GetObjectRequest.builder()
				.bucket(bucketName)
				.key(uploadedFile.getJsonS3Key())
				.build();

			ResponseInputStream<GetObjectResponse> response = s3Client.getObject(getRequest);
			String jsonString = A704.DODREAM.file.service.ObjectJsonReader.read(response);

			// 5. JSON 파싱
			Map<String, Object> jsonData = objectMapper.readValue(jsonString, Map.class);

			// ===== 디버깅: JSON 구조 확인 =====
			log.info("📋 JSON 최상위 키 목록: {}", jsonData.keySet());
			if (jsonData.containsKey("data")) {
				log.info("📋 data 타입: {}", jsonData.get("data").getClass().getName());
			}

			// 6. 개념 Check 필터링
			List<Map<String, Object>> conceptCheckItems = filterConceptCheckFromJson(jsonData);

			if (conceptCheckItems.isEmpty()) {
				throw new RuntimeException("개념 Check 항목을 찾을 수 없습니다.");
			}

			log.info("✅ 개념 Check 항목 {}개 조회 완료", conceptCheckItems.size());

			// 7. 새로운 JSON 구조로 반환
			return Map.of("pdfId", pdfId, "filename", uploadedFile.getOriginalFileName(), "conceptCheckCount",
				conceptCheckItems.size(), "data", conceptCheckItems);

		} catch (A704.DODREAM.authorization.AuthorizationFailure | org.springframework.web.server.ResponseStatusException denied) {
            throw denied;
        } catch (Exception e) {
			log.error("❌ 개념 Check 조회 실패: {}", e.getClass().getSimpleName());
			throw new RuntimeException("개념 Check 조회 실패: " + e.getMessage());
		}
	}

	/**
	 * JSON에서 concept_checks 배열의 title == "개념 Check"인 항목을 index별로 그룹화하는 메서드
	 * <p>
	 * 반환 형식:
	 * [
	 * {
	 * "index": "01",
	 * "index_title": "사회·문화 현상의 이해",
	 * "questions": [
	 * {"question": "...", "answer": "..."},
	 * {"question": "...", "answer": "..."}
	 * ]
	 * }
	 * ]
	 */
	private List<Map<String, Object>> filterConceptCheckFromJson(Map<String, Object> jsonData) {
		// JSON 구조에 따라 분기 처리
		// 1. data 배열 (upload-and-parse 응답) -> concept_checks 필터링
		// 2. chapters 배열 (publish 응답) -> type == "quiz" 필터링

		// ===== 1. chapters 배열 구조 (발행된 자료) 처리 =====
		if (jsonData.containsKey("chapters")) {
			log.info("📋 발행된 자료 형태 감지 (chapters 배열)");
			return filterQuizFromChapters(jsonData);
		}

		// ===== 2. data 배열 구조 (파싱된 자료) 처리 =====
		if (!jsonData.containsKey("data")) {
			log.error("❌ JSON에 'data' 또는 'chapters' 키가 없습니다. 사용 가능한 키: {}", jsonData.keySet());
			throw new RuntimeException("data 또는 chapters 배열이 없습니다. 사용 가능한 키: " + jsonData.keySet());
		}

		Object dataObj = jsonData.get("data");
		if (!(dataObj instanceof List)) {
			log.error("❌ 'data'가 배열이 아닙니다. 타입: {}", dataObj.getClass().getName());
			throw new RuntimeException("data가 배열 형식이 아닙니다.");
		}

		List<Map<String, Object>> dataList = (List<Map<String, Object>>)dataObj;
		if (dataList.isEmpty()) {
			log.warn("⚠️ data 배열이 비어있습니다.");
			throw new RuntimeException("data 배열이 비어있습니다.");
		}

		log.info("🔍 data 배열 크기: {}", dataList.size());

		// ===== 디버깅: 첫 번째 data 항목의 구조 확인 =====
		if (!dataList.isEmpty()) {
			Map<String, Object> firstItem = dataList.get(0);
			log.info("🔍 첫 번째 data 항목의 키: {}", firstItem.keySet());
		}

		// data -> concept_checks에서 개념 Check 찾고 index별로 그룹화
		List<Map<String, Object>> groupedConceptCheckItems = new ArrayList<>();

		for (Map<String, Object> dataItem : dataList) {
			// index와 index_title 추출 (타입 안전하게 처리)
			Object indexObj = dataItem.get("index");
			Object indexTitleObj = dataItem.get("index_title");

			String index = (indexObj != null) ? indexObj.toString() : "";
			String indexTitle = (indexTitleObj != null) ? indexTitleObj.toString() : "";

			log.info("🔍 처리 중인 index: '{}', index_title: '{}'", index, indexTitle);

			// concept_checks 배열 가져오기
			Object conceptChecksObj = dataItem.get("concept_checks");

			if (conceptChecksObj == null) {
				log.info("⚠️ concept_checks 키가 없습니다.");
				continue;
			}

			if (!(conceptChecksObj instanceof List)) {
				log.warn("⚠️ concept_checks가 배열이 아닙니다. 타입: {}", conceptChecksObj.getClass().getName());
				continue;
			}

			List<?> conceptChecks = (List<?>)conceptChecksObj;
			log.info("🔍 concept_checks 배열 크기: {}", conceptChecks.size());

			// 이 index에 해당하는 모든 "개념 Check"의 questions를 모음
			List<Map<String, Object>> allQuestions = new ArrayList<>();

			for (Object conceptCheckObj : conceptChecks) {
				// conceptCheck가 String인지 Map인지 확인
				Map<String, Object> conceptCheck;

				if (conceptCheckObj instanceof String) {
					// JSON 문자열을 파싱
					try {
						conceptCheck = objectMapper.readValue((String)conceptCheckObj, Map.class);
						log.info("🔄 concept_check를 JSON 문자열에서 파싱했습니다.");
					} catch (JsonProcessingException e) {
						log.warn("⚠️ concept_check JSON 파싱 실패: {}", e.getClass().getSimpleName());
						continue;
					}
				} else if (conceptCheckObj instanceof Map) {
					conceptCheck = (Map<String, Object>)conceptCheckObj;
				} else {
					log.warn("⚠️ concept_check 타입이 올바르지 않습니다: {}", conceptCheckObj.getClass().getName());
					continue;
				}

				Object titleObj = conceptCheck.get("title");
				String titleValue = (titleObj != null) ? titleObj.toString() : "";
				log.info("🔍 concept_check title 값: '{}'", titleValue);

				// title == "개념 Check"인 항목의 questions 추가
				if ("개념 Check".equals(titleValue)) {
					log.info("✅ 개념 Check 발견!");

					Object questionsObj = conceptCheck.get("questions");
					List<Map<String, Object>> questions = null;

					if (questionsObj instanceof String) {
						// JSON 문자열을 파싱
						try {
							questions = objectMapper.readValue((String)questionsObj, List.class);
							log.info("🔄 questions를 JSON 문자열에서 파싱했습니다.");
						} catch (JsonProcessingException e) {
							log.warn("⚠️ questions JSON 파싱 실패: {}", e.getClass().getSimpleName());
							continue;
						}
					} else if (questionsObj instanceof List) {
						questions = (List<Map<String, Object>>)questionsObj;
					}

					if (questions != null) {
						// answer에서 숫자 부분 제거하면서 추가
						for (Object questionObj : questions) {
							Map<String, Object> question;

							if (questionObj instanceof String) {
								// JSON 문자열을 파싱
								try {
									question = objectMapper.readValue((String)questionObj, Map.class);
								} catch (JsonProcessingException e) {
									log.warn("⚠️ question JSON 파싱 실패: {}", e.getClass().getSimpleName());
									continue;
								}
							} else if (questionObj instanceof Map) {
								question = (Map<String, Object>)questionObj;
							} else {
								log.warn("⚠️ question 타입이 올바르지 않습니다: {}", questionObj.getClass().getName());
								continue;
							}

							Map<String, Object> cleanedQuestion = new HashMap<>();

							// question 값 안전하게 처리
							Object qObj = question.get("question");
							String questionValue = (qObj != null) ? qObj.toString() : "";
							cleanedQuestion.put("question", questionValue);

							// answer에서 앞의 "숫자. " 패턴 제거
							Object answerObj = question.get("answer");
							String answer = (answerObj != null) ? answerObj.toString() : "";
							if (!answer.isEmpty()) {
								// "1. ", "2. ", "3. " 등의 패턴 제거 (정규식 사용)
								answer = answer.replaceAll("^\\d+\\.\\s*", "");
							}
							cleanedQuestion.put("answer", answer);

							allQuestions.add(cleanedQuestion);
						}

						log.info("✅ questions {} 개 추가됨", questions.size());
					}
				}
			}

			// questions가 있는 경우에만 결과에 추가
			if (!allQuestions.isEmpty()) {
				// LinkedHashMap을 사용하여 필드 순서 보장
				Map<String, Object> groupedItem = new java.util.LinkedHashMap<>();
				groupedItem.put("index", index);
				groupedItem.put("index_title", indexTitle);
				groupedItem.put("questions", allQuestions);

				groupedConceptCheckItems.add(groupedItem);
				log.info("✅ index '{}' 그룹 생성 완료 (총 {} 개 questions)", index, allQuestions.size());
			}
		}

		return groupedConceptCheckItems;
	}

	@Transactional
	public Map<String, Object> extractConceptCheck(Long pdfId, Long userId) {
		try {
			// 1. DB에서 PDF 정보 조회
			UploadedFile uploadedFile = uploadedFileRepository.findById(pdfId)
				.orElseThrow(() -> new RuntimeException("PDF를 찾을 수 없습니다."));

			// 2. 권한 검증
			if (!uploadedFile.getUploaderId().equals(userId)) {
				throw new RuntimeException("권한이 없습니다.");
			}

			// 3. JSON S3 키 확인 (파싱된 JSON이 있어야 함)
			if (uploadedFile.getJsonS3Key() == null || uploadedFile.getJsonS3Key().isEmpty()) {
				throw new RuntimeException("파싱된 JSON이 없습니다. 먼저 PDF를 파싱해주세요.");
			}

			// 4. S3에서 JSON 다운로드
			GetObjectRequest getRequest = GetObjectRequest.builder()
				.bucket(bucketName)
				.key(uploadedFile.getJsonS3Key())
				.build();

			ResponseInputStream<GetObjectResponse> response = s3Client.getObject(getRequest);
			String jsonString = A704.DODREAM.file.service.ObjectJsonReader.read(response);

			// 5. JSON 파싱
			Map<String, Object> jsonData = objectMapper.readValue(jsonString, Map.class);

			// 6. 개념 Check 필터링 (공통 메서드 사용)
			List<Map<String, Object>> conceptCheckItems = filterConceptCheckFromJson(jsonData);

			if (conceptCheckItems.isEmpty()) {
				throw new RuntimeException("개념 Check 항목을 찾을 수 없습니다.");
			}

			log.info("✅ 개념 Check 항목 {}개 추출 완료", conceptCheckItems.size());

			// 7. FastAPI로 전송할 데이터 구성
			Map<String, Object> requestData = new HashMap<>();
			requestData.put("concept_checks", conceptCheckItems);

			// 8. FastAPI 호출 (개념 Check 가공)
			String fastApiEndpoint = fastApiUrl + "/document/process-concept-check";

			ResponseEntity<Map> fastApiResponse = webClient.post()
				.uri(fastApiEndpoint)
				.bodyValue(requestData)
				.retrieve()
				.onStatus(status -> status.is4xxClientError() || status.is5xxServerError(),
					clientResponse -> clientResponse.bodyToMono(String.class)
						.map(errorBody -> new RuntimeException("FastAPI 에러: " + errorBody)))
				.toEntity(Map.class)
				.block();

			if (fastApiResponse.getBody() == null) {
				throw new RuntimeException("FastAPI 응답이 비어있습니다.");
			}

			Map<String, Object> processedData = fastApiResponse.getBody();

			log.info("✅ FastAPI 가공 완료");

			// 9. 가공된 JSON을 S3에 저장
			String conceptCheckS3Key = uploadConceptCheckJsonToS3(uploadedFile.getS3Key(), processedData,
				userId.toString());

			// 10. DB 업데이트
			uploadedFile.setConceptCheckJsonS3Key(conceptCheckS3Key);
			uploadedFileRepository.save(uploadedFile);

			log.info("✅ 개념 Check 추출 및 저장 완료: pdfId={}", pdfId);

			return Map.of("pdfId", pdfId, "filename", uploadedFile.getOriginalFileName(), "processedData",
				processedData);

		} catch (A704.DODREAM.authorization.AuthorizationFailure | org.springframework.web.server.ResponseStatusException denied) {
            throw denied;
        } catch (Exception e) {
			log.error("❌ 개념 Check 추출 실패: {}", e.getClass().getSimpleName());
			throw new RuntimeException("개념 Check 추출 실패: " + e.getMessage());
		}
	}

	/**
	 * 개념 Check JSON을 S3에 업로드
	 *
	 * @param pdfS3Key:         원본 PDF의 S3 키
	 * @param conceptCheckData: 가공된 개념 Check 데이터
	 * @param username:         사용자 ID
	 * @return S3에 저장된 개념 Check JSON의 키
	 */
	private String uploadConceptCheckJsonToS3(String pdfS3Key, Map<String, Object> conceptCheckData, String username) {
		try {
			// PDF 경로에서 파일명 추출
			String filename = pdfS3Key.substring(pdfS3Key.lastIndexOf("/") + 1).replace(".pdf", "");

			// 개념 Check JSON S3 키 생성
			// concept-check-json/UUID.json
			String conceptCheckS3Key = pdfS3Key.replace(uploadPrefix + "/", "concept-check-json/")
				.replace(".pdf", ".json");

			// JSON을 예쁘게 포맷팅
			String jsonString = objectMapper.writerWithDefaultPrettyPrinter().writeValueAsString(conceptCheckData);

			// S3에 업로드
			PutObjectRequest putRequest = PutObjectRequest.builder()
				.bucket(bucketName)
				.key(conceptCheckS3Key)
				.contentType("application/json")
				.metadata(
					Map.of("original-pdf", pdfS3Key, "processed-at", LocalDateTime.now().toString(), "owner", username,
						"type", "concept-check"))
				.build();

			s3Client.putObject(putRequest, RequestBody.fromString(jsonString));

			log.info("✅ 개념 Check JSON S3 저장 완료: {}", conceptCheckS3Key);

			return conceptCheckS3Key;

		} catch (JsonProcessingException e) {
			throw new RuntimeException("JSON 직렬화 실패: " + e.getMessage());
		} catch (S3Exception e) {
			throw new RuntimeException("S3 업로드 실패: " + e.getMessage());
		}
	}

	/**
	 * 스크린리더 친화 형태로 JSON → TXT 변환
	 *
	 * @param pdfId  PDF ID
	 * @param userId 사용자 ID
	 * @return 읽기 최적화된 TXT
	 */
	public String extractTextFromJson(Long pdfId, Long userId) {

		Map<String, Object> jsonResult = getJsonFromS3(pdfId, userId);
		Map<String, Object> parsedData = (Map<String, Object>)jsonResult.get("parsedData");

		if (parsedData == null) {
			throw new RuntimeException("파싱된 데이터가 없습니다.");
		}

		StringBuilder text = new StringBuilder();

		// -----------------------------
		// 파일명
		// -----------------------------
		if (jsonResult.containsKey("filename")) {
			text.append("파일명: ").append(jsonResult.get("filename")).append("\n\n");
		}

		// -----------------------------
		// 목차
		// -----------------------------
		if (parsedData.containsKey("indexes")) {
			List<String> indexes = (List<String>)parsedData.get("indexes");
			if (indexes != null && !indexes.isEmpty()) {
				text.append("목차\n\n");
				for (String index : indexes) {
					text.append(index).append("\n");
				}
				text.append("\n");
			}
		}

		// -----------------------------
		// 본문 내용
		// -----------------------------
		List<Map<String, Object>> dataList = (List<Map<String, Object>>)parsedData.get("data");

		if (dataList != null) {
			for (Map<String, Object> dataItem : dataList) {

				// index + index_title
				if (dataItem.containsKey("index") && dataItem.containsKey("index_title")) {
					text.append(dataItem.get("index")).append(" ").append(dataItem.get("index_title")).append("\n\n");
				}

				// titles
				List<Map<String, Object>> titles = (List<Map<String, Object>>)dataItem.get("titles");
				if (titles != null) {
					for (Map<String, Object> titleItem : titles) {

						// title
						if (titleItem.containsKey("title")) {
							text.append(titleItem.get("title")).append("\n");
						}

						// s_titles
						List<Map<String, Object>> sTitles = (List<Map<String, Object>>)titleItem.get("s_titles");
						if (sTitles != null) {
							for (Map<String, Object> sTitleItem : sTitles) {

								// s_title
								if (sTitleItem.containsKey("s_title")) {
									text.append("  ").append(sTitleItem.get("s_title")).append("\n");
								}

								// contents
								String contents = (String)sTitleItem.get("contents");
								if (contents != null && !contents.isBlank()) {
									text.append("    ").append(contents).append("\n");
								}

								// ss_titles
								List<Map<String, Object>> ssTitles = (List<Map<String, Object>>)sTitleItem.get(
									"ss_titles");

								if (ssTitles != null) {
									for (Map<String, Object> ssTitleItem : ssTitles) {

										if (ssTitleItem.containsKey("ss_title")) {
											text.append("    - ").append(ssTitleItem.get("ss_title")).append("\n");
										}

										String ssContents = (String)ssTitleItem.get("contents");
										if (ssContents != null && !ssContents.isBlank()) {
											text.append("      ").append(ssContents).append("\n");
										}
									}
								}
								text.append("\n");
							}
						}

						text.append("\n");
					}
				}

				// concept_checks 처리
				List<Map<String, Object>> conceptChecks = (List<Map<String, Object>>)dataItem.get("concept_checks");
				if (conceptChecks != null && !conceptChecks.isEmpty()) {
					for (Map<String, Object> conceptCheck : conceptChecks) {

						// title (예: "개념 Check")
						if (conceptCheck.containsKey("title")) {
							text.append(conceptCheck.get("title")).append("\n");
						}

						// questions
						Object questionsObj = conceptCheck.get("questions");
						if (questionsObj != null) {
							List<Map<String, Object>> questions = null;

							// questions가 List 또는 String으로 올 수 있음
							if (questionsObj instanceof List) {
								questions = (List<Map<String, Object>>)questionsObj;
							} else if (questionsObj instanceof String) {
								try {
									questions = objectMapper.readValue((String)questionsObj, List.class);
								} catch (JsonProcessingException e) {
									log.warn("questions JSON 파싱 실패: {}", e.getClass().getSimpleName());
								}
							}

							if (questions != null) {
								for (Map<String, Object> questionItem : questions) {
									String question =
										questionItem.get("question") != null ? questionItem.get("question").toString() :
											"";
									String answer =
										questionItem.get("answer") != null ? questionItem.get("answer").toString() : "";

									if (!question.isBlank()) {
										text.append("  질문: ").append(question).append("\n");
									}
									if (!answer.isBlank()) {
										text.append("  답: ").append(answer).append("\n");
									}
									text.append("\n");
								}
							}
						}

						text.append("\n");
					}
				}
			}
		}

		// -----------------------------
		// 메타데이터
		// -----------------------------
		if (jsonResult.containsKey("parsedAt")) {
			text.append("\n파싱 일시: ").append(jsonResult.get("parsedAt")).append("\n");
		}

		String result = text.toString().trim();
		return result.isEmpty() ? "추출된 텍스트가 없습니다." : result;
	}

	/**
	 * chapters 배열에서 type == "quiz"인 항목만 필터링
	 * (발행된 자료용)
	 *
	 * @param jsonData chapters 배열을 포함한 JSON 데이터
	 * @return 퀴즈 데이터 목록
	 */
	private List<Map<String, Object>> filterQuizFromChapters(Map<String, Object> jsonData) {
		Object chaptersObj = jsonData.get("chapters");

		if (!(chaptersObj instanceof List)) {
			log.error("❌ 'chapters'가 배열이 아닙니다. 타입: {}", chaptersObj.getClass().getName());
			throw new RuntimeException("chapters가 배열 형식이 아닙니다.");
		}

		List<Map<String, Object>> chapters = (List<Map<String, Object>>)chaptersObj;
		if (chapters.isEmpty()) {
			log.warn("⚠️ chapters 배열이 비어있습니다.");
			throw new RuntimeException("chapters 배열이 비어있습니다.");
		}

		log.info("🔍 chapters 배열 크기: {}", chapters.size());

		List<Map<String, Object>> quizItems = new ArrayList<>();

		for (Map<String, Object> chapter : chapters) {
			Object typeObj = chapter.get("type");
			String type = (typeObj != null) ? typeObj.toString() : "";

			// type == "quiz"인 항목만 추출
			if ("quiz".equals(type)) {
				log.info("✅ quiz 타입 챕터 발견! id={}", chapter.get("id"));

				// qa 배열에서 question과 answer 추출
				Object qaObj = chapter.get("qa");
				List<Map<String, Object>> qaList = null;

				if (qaObj instanceof List) {
					qaList = (List<Map<String, Object>>)qaObj;
				}

				if (qaList != null && !qaList.isEmpty()) {
					// 각 qa 항목을 questions 형태로 변환
					List<Map<String, Object>> questions = new ArrayList<>();

					for (Map<String, Object> qaItem : qaList) {
						Map<String, Object> question = new HashMap<>();

						Object questionObj = qaItem.get("question");
						Object answerObj = qaItem.get("answer");

						String questionValue = (questionObj != null) ? questionObj.toString() : "";
						String answerValue = (answerObj != null) ? answerObj.toString() : "";

						question.put("question", questionValue);
						question.put("answer", answerValue);

						questions.add(question);
					}

					// 챕터 제목을 index_title로 사용
					Object titleObj = chapter.get("title");
					String title = (titleObj != null) ? titleObj.toString() : "";

					// 결과 항목 생성
					Map<String, Object> quizItem = new java.util.LinkedHashMap<>();
					quizItem.put("index", chapter.get("id"));  // id를 index로 사용
					quizItem.put("index_title", title);
					quizItem.put("questions", questions);

					quizItems.add(quizItem);

					log.info("✅ quiz 항목 추가 완료: {} questions", questions.size());
				}
			}
		}

		log.info("✅ 총 {} 개의 quiz 항목 추출 완료", quizItems.size());

		return quizItems;
	}

}
