package A704.DODREAM.material.service;

import A704.DODREAM.file.enums.PostStatus;
import A704.DODREAM.file.service.CloudFrontService;
import A704.DODREAM.material.dto.PublishRequest;
import A704.DODREAM.material.dto.PublishResponseDto;
import A704.DODREAM.file.entity.UploadedFile;
import A704.DODREAM.file.repository.UploadedFileRepository;
import A704.DODREAM.global.exception.CustomException;
import A704.DODREAM.global.exception.constant.ErrorCode;
import A704.DODREAM.material.dto.PublishedMaterialListResponse;
import A704.DODREAM.material.entity.Material;
import A704.DODREAM.material.enums.LabelColor;
import A704.DODREAM.material.repository.MaterialRepository;
import A704.DODREAM.quiz.service.QuizService;
import A704.DODREAM.user.entity.User;
import A704.DODREAM.user.repository.UserRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.transaction.Transactional;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;

import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Stream;

@Service
@Slf4j
@RequiredArgsConstructor
public class PublishService {
    private final A704.DODREAM.authorization.AuthorizationPolicy policy;

	private final UserRepository userRepository;
	private final MaterialRepository materialRepository;
	private final UploadedFileRepository uploadedFileRepository;
	private final S3Client s3Client;
	private final ObjectMapper objectMapper;
	private final WebClient webClient; // (WebClientConfig Bean으로 생성되었다고 가정)
	private final CloudFrontService cloudFrontService; // (CloudFrontService Bean으로 생성되었다고 가정)
	private final QuizService quizService;

	@Value("${aws.s3.bucket}")
	private String bucketName;

	@Value("${fastapi.url}")
	private String fastApiUrl;

	@Transactional
	public PublishResponseDto publishJsonWithIds(
		Long pdfId,
		Long userId,
		PublishRequest publishRequest,
		String authorizationHeader // (신규) Controller에서 JWT 토큰 수신
	) {

        policy.ownedFile(userId, pdfId);
        if (publishRequest.getQuizzes() != null && !publishRequest.getQuizzes().isEmpty()) {
            Long existingId = materialRepository.findByUploadedFileId(pdfId).map(Material::getId).orElse(null);
            quizService.validateEdits(existingId, publishRequest.getQuizzes());
        }
		User teacher = userRepository.findById(userId)
			.orElseThrow(() -> new CustomException(ErrorCode.USER_NOT_FOUND));

		UploadedFile uploadedFile;
		Material material; // (수정) FastAPI에서 사용하기 위해 밖으로 선언

		try {
			uploadedFile = uploadedFileRepository.findById(pdfId)
				.orElseThrow(() -> new CustomException(ErrorCode.FILE_NOT_FOUND));

			if (uploadedFile.getJsonS3Key() == null) {
				throw new CustomException(ErrorCode.FILE_PARSING_FAILED);
			}

			// ... (기존 S3 업로드 로직) ...
			String jsonString = objectMapper.writerWithDefaultPrettyPrinter()
				.writeValueAsString(publishRequest.getEditedJson());

			PutObjectRequest putRequest = PutObjectRequest.builder()
				// ... (기존 PutRequest 설정) ...
				.bucket(bucketName)
				.key(uploadedFile.getJsonS3Key())
				.contentType("application/json")
				.metadata(Map.of(
					"original-pdf", uploadedFile.getS3Key(),
					"parsed-at", uploadedFile.getParsedAt() != null
						? uploadedFile.getParsedAt().toString() : "",
					"published-at", LocalDateTime.now().toString(),
					"owner", userId.toString()
				))
				.build();

			s3Client.putObject(
				putRequest,
				RequestBody.fromString(jsonString, StandardCharsets.UTF_8)
			);

			// --- (신규) type: "quiz"인 데이터만 필터링하여 별도 S3에 저장 ---
			try {
				List<Map<String, Object>> quizChapters = filterQuizChapters(publishRequest.getEditedJson());

				if (!quizChapters.isEmpty()) {
					// Quiz 데이터를 새로운 JSON 구조로 생성
					Map<String, Object> quizJson = Map.of("chapters", quizChapters);
					String quizJsonString = objectMapper.writerWithDefaultPrettyPrinter()
						.writeValueAsString(quizJson);

					// S3 키 생성: quiz-json/{userId}/{pdfId}_quiz.json
					String quizJsonS3Key = String.format("quiz-json/%s/%s_quiz.json", userId, pdfId);

					// S3에 Quiz JSON 저장
					PutObjectRequest quizPutRequest = PutObjectRequest.builder()
						.bucket(bucketName)
						.key(quizJsonS3Key)
						.contentType("application/json")
						.metadata(Map.of(
							"original-pdf", uploadedFile.getS3Key(),
							"published-at", LocalDateTime.now().toString(),
							"owner", userId.toString(),
							"type", "quiz-only"
						))
						.build();

					s3Client.putObject(
						quizPutRequest,
						RequestBody.fromString(quizJsonString, StandardCharsets.UTF_8)
					);

					// DB에 Quiz JSON S3 키 저장
					uploadedFile.setQuestionJsonS3Key(quizJsonS3Key);

					log.info("✅ Quiz 데이터 S3 저장 완료 [S3 Key: {}]", quizJsonS3Key);
				} else {
					log.info("⚠️ Quiz 데이터가 없어서 별도 저장하지 않습니다.");
				}
			} catch (Exception quizError) {
				// Quiz 저장 실패는 발행 자체를 롤백하지 않음
				log.error("❗️ Quiz 데이터 저장 실패: {}", quizError.getMessage(), quizError);
			}
			// --- (신규) Quiz 필터링 및 저장 종료 ---

			Optional<Material> materialOpt = materialRepository.findByUploadedFileIdAndDeletedAtIsNull(uploadedFile.getId());

			// Material material; // (수정) 밖으로 이동
			if(materialOpt.isPresent()){
				material = materialOpt.get();
				material.setTitle(publishRequest.getMaterialTitle());
				material.setLabel(publishRequest.getLabelColor());
				material.setUpdatedAt(LocalDateTime.now());
                material.setPostStatus(PostStatus.PUBLISHED);
			} else {
				material = Material.builder()
					.uploadedFile(uploadedFile)
					.teacher(teacher)
					.title(publishRequest.getMaterialTitle())
					.label(publishRequest.getLabelColor())
                    .postStatus(PostStatus.PUBLISHED)
					.build();
			}

			// (중요) FastAPI에 document_id(Material ID)를 보내야 하므로,
			// S3 업로드와 Material 저장을 먼저 수행합니다.
			materialRepository.save(material);

			log.info("✅ 자료 발행 및 Material 저장 완료 [Material ID: {}]", material.getId());

			// ===============================================================
			// [추가된 로직] 5. QuizService를 통해 퀴즈 DB 저장
			// ===============================================================
			try {
				// PublishRequest에 List<QuizSaveDto> quizzes 필드가 있다고 가정
				if (publishRequest.getQuizzes() != null && !publishRequest.getQuizzes().isEmpty()) {
					log.info("퀴즈 DB 저장을 시작합니다. (Material ID: {}, 퀴즈 수: {})",
						material.getId(), publishRequest.getQuizzes().size());

					// QuizService 호출
					quizService.saveQuizzes(material.getId(), userId, publishRequest.getQuizzes());

					log.info("✅ 퀴즈 DB 저장 완료");
				} else {
					log.info("ℹ️ 저장할 퀴즈 데이터가 없습니다.");
				}
			} catch (Exception quizDbError) {
				// 퀴즈 DB 저장이 실패했을 때 전체 발행을 롤백할지 여부 결정 필요
				// 여기서는 중요 데이터이므로 에러를 로그에 남기고,
				// 필요하다면 throw하여 전체 트랜잭션을 롤백시킵니다.
				log.error("❗️ 퀴즈 DB 저장 실패: {}", quizDbError.getMessage(), quizDbError);
				throw new RuntimeException("퀴즈 저장 중 오류가 발생했습니다.", quizDbError);
			}
			// ===============================================================

            // AI uses an independent DB connection, so the newly published relationship must be committed first.
            final Long documentId = material.getId();
            final String objectKey = uploadedFile.getJsonS3Key();
            org.springframework.transaction.support.TransactionSynchronizationManager.registerSynchronization(
                new org.springframework.transaction.support.TransactionSynchronization() {
                    @Override public void afterCommit() { enqueueEmbedding(documentId, objectKey, authorizationHeader); }
                });

		} catch (A704.DODREAM.authorization.AuthorizationFailure | org.springframework.web.server.ResponseStatusException denied) {
            throw denied;
        } catch (Exception e) {
			log.error("JSON 발행 실패: pdfId={}, error={}", pdfId, e.getMessage(), e);
			throw new RuntimeException("JSON 발행 실패: " + e.getMessage());
		}

		return PublishResponseDto.builder()
			.success(true)
			.pdfId(pdfId)
			.filename(uploadedFile.getOriginalFileName())
			.jsonS3Key(uploadedFile.getJsonS3Key())
			.publishedAt(LocalDateTime.now())
			.message("문서가 성공적으로 발행되었습니다.")
			.build();
	}

	//    private void addIds(Map<String, Object> jsonData) {
	//        Map<String, Object> parsedData = (Map<String, Object>) jsonData.get("parsedData");
	//        if(parsedData == null){
	//            return;
	//        }
	//
	//        List<Map<String, Object>> dataList = (List<Map<String, Object>>) parsedData.get("data");
	//        if(dataList == null || dataList.isEmpty()) {
	//            return;
	//        }
	//
	//        for(Map<String, Object> content : dataList) {
	//            List<Map<String, Object>> titles = (List<Map<String, Object>>) content.get("titles");
	//
	//            if(titles != null){
	//                for(int i = 0; i < titles.size(); i++){
	//                    Map<String, Object> title = titles.get(i);
	//                    titles.set(i, addIdToTop(title));
	//
	//                    List<Map<String, Object>> sTitles = (List<Map<String, Object>>) title.get("s_titles");
	//                    if(sTitles != null){
	//                        for(int j = 0; j < sTitles.size(); j++){
	//                            Map<String, Object> sTitle = sTitles.get(j);
	//                            sTitles.set(j, addIdToTop(sTitle));
	//
	//                            List<Map<String, Object>> ssTitles = (List<Map<String, Object>>) sTitle.get("ss_titles");
	//                            if(ssTitles != null){
	//                                for(int k = 0; k < ssTitles.size(); k++){
	//                                    Map<String, Object> ssTitle = ssTitles.get(k);
	//                                    ssTitles.set(k, addIdToTop(ssTitle));
	//                                }
	//                            }
	//                        }
	//                    }
	//                }
	//            }
	//        }
	//    }
	//
	//    private Map<String, Object> addIdToTop(Map<String, Object> map) {
	//        if(map.containsKey("id") && map.get("id") != null) {
	//            return map;
	//        }
	//        // LinkedHashMap으로 새로운 맵 생성 (순서 보장)
	//        Map<String, Object> newMap = new LinkedHashMap<>();
	//
	//        // id를 가장 먼저 추가
	//        newMap.put("id", UUID.randomUUID().toString());
	//
	//        // 나머지 기존 데이터 추가
	//        newMap.putAll(map);
	//
	//        return newMap;
	//    }

	public PublishedMaterialListResponse getPublishedMaterialList(Long userId) {
        policy.teacher(userId);

		User teacher = userRepository.findById(userId)
			.orElseThrow(() -> new CustomException(ErrorCode.USER_NOT_FOUND));


		List<Material> materials = materialRepository.findAllByTeacherIdWithUploadedFile(teacher.getId()).stream()
            .filter(material -> userId.equals(material.getUploadedFile().getUploaderId())).toList();

        return PublishedMaterialListResponse.from(materials);
    }

    @Transactional
    public void updateLabel(Long materialId, Long userId, LabelColor label){
        policy.owned(userId, materialId);
        Material material = materialRepository.findById(materialId)
                .orElseThrow(() -> new CustomException(ErrorCode.MATERIAL_NOT_FOUND));

        if(!material.getTeacher().getId().equals(userId)){
            throw new CustomException(ErrorCode.FORBIDDEN);
        }

        material.setLabel(label);
    }

    @Transactional
    public void deleteMaterial(Long userId, Long materialId) {
        policy.owned(userId, materialId);
        Material material = materialRepository.findByIdAndTeacherIdAndDeletedAtIsNull(materialId, userId)
                        .orElseThrow(() -> new CustomException(ErrorCode.FORBIDDEN));

        UploadedFile uploadedFile = material.getUploadedFile();

        Stream.of(
                        uploadedFile.getS3Key(),
                        uploadedFile.getJsonS3Key(),
                        uploadedFile.getConceptCheckJsonS3Key()
                )
                .filter(Objects::nonNull)
                .forEach(s3Key -> {
                    try {
                        DeleteObjectRequest deleteRequest = DeleteObjectRequest.builder()
                                .bucket(bucketName)
                                .key(s3Key)
                                .build();
                        s3Client.deleteObject(deleteRequest);
                        log.info("S3 파일 삭제 완료: {}", s3Key);
                    } catch (Exception e) {
                        log.error("S3 파일 삭제 실패: {}, 에러: {}", s3Key, e.getMessage());
                    }
                });

        material.softDelete();
        materialRepository.save(material);
    }

	/**
	 * editedJson에서 type이 "quiz"인 chapters만 필터링하는 메서드
	 *
	 * @param editedJson 발행 요청에서 받은 전체 JSON 데이터
	 * @return type: "quiz"인 chapter 목록
	 */
	private List<Map<String, Object>> filterQuizChapters(Map<String, Object> editedJson) {
		List<Map<String, Object>> quizChapters = new ArrayList<>();

		// editedJson에서 chapters 배열 가져오기
		Object chaptersObj = editedJson.get("chapters");

		if (chaptersObj == null || !(chaptersObj instanceof List)) {
			log.warn("⚠️ editedJson에 'chapters' 배열이 없습니다.");
			return quizChapters;
		}

		List<Map<String, Object>> chapters = (List<Map<String, Object>>) chaptersObj;

		// type이 "quiz"인 항목만 필터링
		for (Map<String, Object> chapter : chapters) {
			Object typeObj = chapter.get("type");

			if (typeObj != null && "quiz".equals(typeObj.toString())) {
				quizChapters.add(chapter);
			}
		}

		log.info("🔍 전체 chapters: {}개, quiz type: {}개", chapters.size(), quizChapters.size());

		return quizChapters;
	}

    private void enqueueEmbedding(Long materialId, String objectKey, String authorization) {
        try {
            webClient.post().uri(fastApiUrl + "/rag/embeddings/create")
                .header("Authorization", authorization)
                .bodyValue(Map.of("document_id", materialId.toString(), "s3_url", cloudFrontService.generateSignedUrl(objectKey)))
                .retrieve().toBodilessEntity().block();
        } catch (Exception failure) {
            // Publishing remains committed; no bearer, signed URL or upstream body is logged.
            log.warn("Embedding request failed after publishing material {}", materialId);
        }
    }
}
