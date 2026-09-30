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
    private final A704.DODREAM.indexing.IndexingService indexingService;
    private final A704.DODREAM.indexing.IndexingStore indexingStore;

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

    public PublishResponseDto publishJsonWithIds(Long pdfId, Long userId, PublishRequest request, String authorizationHeader) {
        var publication=indexingService.publish(userId,pdfId,request);
        return PublishResponseDto.builder().success(true).pdfId(pdfId).materialId(publication.materialId())
            .filename(publication.filename()).jsonS3Key(publication.jsonKey()).publishedAt(LocalDateTime.now())
            .indexing(publication.indexing()).message("문서가 저장되었으며 검색 준비 상태를 확인할 수 있습니다.").build();
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

        return PublishedMaterialListResponse.from(materials, indexingStore.materialSummaries(userId, materials.stream().map(Material::getId).toList()));
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

}
