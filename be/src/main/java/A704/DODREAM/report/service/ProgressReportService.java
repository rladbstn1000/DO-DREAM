package A704.DODREAM.report.service;

import A704.DODREAM.global.exception.CustomException;
import A704.DODREAM.global.exception.constant.ErrorCode;
import A704.DODREAM.material.entity.Material;
import A704.DODREAM.material.entity.MaterialShare;
import A704.DODREAM.material.repository.MaterialRepository;
import A704.DODREAM.material.repository.MaterialShareRepository;
import A704.DODREAM.progress.entity.StudentMaterialProgress;
import A704.DODREAM.report.dto.AverageProgressResponse;
import A704.DODREAM.report.dto.ChapterProgressDto;
import A704.DODREAM.report.dto.ProgressReportResponse;
import A704.DODREAM.report.dto.UpdateProgressResponse;
import A704.DODREAM.report.repository.StudentMaterialProgressRepository;
import A704.DODREAM.user.entity.User;
import A704.DODREAM.user.repository.UserRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 학습 진행률 리포트 서비스
 * Chapter와 Section 기반 진행률 계산
 */
@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ProgressReportService {
    private final A704.DODREAM.authorization.AuthorizationPolicy policy;

    private final StudentMaterialProgressRepository progressRepository;
    private final MaterialRepository materialRepository;
    private final MaterialShareRepository materialShareRepository;
    private final UserRepository userRepository;
    private final S3Client s3Client;
    private final ObjectMapper objectMapper;

    @Value("${aws.s3.bucket}")
    private String bucketName;

    /**
     * 특정 학생의 특정 교재에 대한 진행률 리포트 조회
     */
    public ProgressReportResponse getProgressReport(Long studentId, Long materialId, Long actorId) {
        policy.studentHistory(actorId, studentId, materialId);
        // 1. 학생 조회
        User student = userRepository.findById(studentId)
                .orElseThrow(() -> new CustomException(ErrorCode.USER_NOT_FOUND));

        // 2. 공유 권한 확인
        MaterialShare share = materialShareRepository.findByStudentIdAndMaterialId(studentId, materialId)
                .orElseThrow(() -> new CustomException(ErrorCode.MATERIAL_NOT_FOUND));

        Material material = share.getMaterial();

        // 3. 진행 상태 조회
        StudentMaterialProgress progress = progressRepository
                .findByStudentIdAndMaterialId(studentId, materialId)
                .orElse(null);

        // 4. DB 값으로 진행률 계산
        int currentPage = progress != null && progress.getCurrentPage() != null ? progress.getCurrentPage() : 0;
        int totalPages = progress != null && progress.getTotalPages() != null ? progress.getTotalPages() : 1;
        
        double overallProgress = totalPages > 0
                ? (double) currentPage / totalPages * 100.0
                : 0.0;
        
        log.info("진행률 조회: currentPage={}/{} = {}%", currentPage, totalPages, overallProgress);

        return ProgressReportResponse.builder()
                .studentId(student.getId())
                .studentName(student.getName())
                .materialId(material.getId())
                .materialTitle(material.getTitle())
                .totalChapters(totalPages)  // totalPages = 총 챕터/섹션 수
                .completedChapters(currentPage >= totalPages ? totalPages : 0)
                .totalSections(totalPages)
                .completedSections(currentPage)
                .overallProgressPercentage(Math.round(overallProgress * 100.0) / 100.0)
                .currentChapterNumber(currentPage < totalPages ? currentPage + 1 : totalPages)
                .currentChapterTitle(null)  // 챕터 제목은 앱에서 관리
                .lastAccessedAt(progress != null ? progress.getLastAccessedAt() : null)
                .completedAt(progress != null ? progress.getCompletedAt() : null)
                .chapterProgress(new ArrayList<>())  // 상세 챕터 정보는 제공하지 않음
                .build();
    }

    /**
     * 특정 학생의 모든 교재에 대한 진행률 요약 조회
     */
    public List<ProgressReportResponse> getAllProgressReports(Long studentId, Long actorId) {
        policy.historySubject(actorId, studentId);
        // 학생 조회
        User student = userRepository.findById(studentId)
                .orElseThrow(() -> new CustomException(ErrorCode.USER_NOT_FOUND));

        // 공유받은 모든 교재 조회
        List<MaterialShare> shares = materialShareRepository.findByStudentId(studentId);

        List<ProgressReportResponse> reports = new ArrayList<>();
        for (MaterialShare share : shares) {
            if (policy.historyVisible(actorId, studentId, share.getMaterial())) {
                reports.add(getProgressReport(studentId, share.getMaterial().getId(), actorId));
            }
        }

        return reports;
    }

    /**
     * S3에서 Material JSON 가져오기
     */
    private Map<String, Object> getMaterialJsonFromS3(Material material) {
        if (material.getUploadedFile() == null) {
            log.error("UploadedFile이 null입니다. materialId={}", material.getId());
            throw new CustomException(ErrorCode.FILE_PARSING_FAILED);
        }

        if (material.getUploadedFile().getJsonS3Key() == null) {
            log.error("JSON S3 Key가 null입니다. materialId={}, fileId={}",
                    material.getId(), material.getUploadedFile().getId());
            throw new CustomException(ErrorCode.FILE_PARSING_FAILED);
        }

        try {
            String s3Key = material.getUploadedFile().getJsonS3Key();
            log.info("S3에서 JSON 조회 시도: bucket={}, key={}", bucketName, s3Key);

            GetObjectRequest getRequest = GetObjectRequest.builder()
                    .bucket(bucketName)
                    .key(s3Key)
                    .build();

            ResponseInputStream<GetObjectResponse> response = s3Client.getObject(getRequest);
            String jsonString = A704.DODREAM.file.service.ObjectJsonReader.read(response);

            log.info("S3에서 JSON 조회 성공: materialId={}, size={} bytes",
                    material.getId(), jsonString.length());

            return objectMapper.readValue(jsonString, Map.class);
        } catch (Exception e) {
            log.error("S3에서 JSON 조회 실패: materialId={}, error={}",
                    material.getId(), e.getMessage(), e);
            throw new RuntimeException("JSON 조회 실패: " + e.getMessage());
        }
    }

    /**
     * currentPage를 콘텐츠 페이지로 변환 (퀴즈 챕터 제외)
     * 예: 챕터 1-3(콘텐츠), 4(퀴즈), 5-6(콘텐츠) → currentPage=5 → contentPage=4
     */
    private int convertToContentPage(List<Map<String, Object>> chapters, int currentPage) {
        int quizCountBeforeCurrent = 0;

        // currentPage 이전에 나온 퀴즈 챕터 개수 계산
        for (int i = 0; i < Math.min(currentPage, chapters.size()); i++) {
            Map<String, Object> chapter = chapters.get(i);

            // 챕터 타입 확인
            String chapterType;
            if (chapter.containsKey("index")) {
                // 이전 구조
                List<Map<String, Object>> conceptChecks = (List<Map<String, Object>>) chapter.get("concept_checks");
                chapterType = (conceptChecks != null && !conceptChecks.isEmpty()) ? "quiz" : "content";
            } else {
                // 새로운 구조
                chapterType = (String) chapter.getOrDefault("type", "content");
            }

            if ("quiz".equals(chapterType)) {
                quizCountBeforeCurrent++;
            }
        }

        // 전체 페이지에서 퀴즈 개수를 빼서 콘텐츠 페이지 반환
        int contentPage = currentPage - quizCountBeforeCurrent;
        log.debug("퀴즈 개수: {}, 전체 페이지: {} → 콘텐츠 페이지: {}",
                quizCountBeforeCurrent, currentPage, contentPage);

        return Math.max(1, contentPage);
    }

    /**
     * 챕터별 진행률 계산
     * 두 가지 JSON 구조를 모두 지원
     */
    private List<ChapterProgressDto> calculateChapterProgress(
            List<Map<String, Object>> chapters,
            StudentMaterialProgress progress) {

        List<ChapterProgressDto> result = new ArrayList<>();
        // DB에 저장된 currentPage는 이미 콘텐츠 페이지 기준 (퀴즈 제외)
        int contentCurrentPage = progress != null ? progress.getCurrentPage() : 1;
        log.info("콘텐츠 페이지 기준 currentPage: {}", contentCurrentPage);

        int cumulativeSections = 0;

        for (int i = 0; i < chapters.size(); i++) {
            Map<String, Object> chapter = chapters.get(i);

            // 챕터 ID와 제목 추출 (두 가지 구조 지원)
            String chapterId;
            String chapterTitle;
            String chapterType;

            if (chapter.containsKey("index")) {
                // 이전 구조
                chapterId = (String) chapter.get("index");
                chapterTitle = (String) chapter.get("index_title");
                // concept_checks가 있으면 quiz 타입으로 간주
                List<Map<String, Object>> conceptChecks = (List<Map<String, Object>>) chapter.get("concept_checks");
                chapterType = (conceptChecks != null && !conceptChecks.isEmpty()) ? "quiz" : "content";
            } else {
                // 새로운 구조
                chapterId = (String) chapter.get("id");
                chapterTitle = (String) chapter.get("title");
                chapterType = (String) chapter.getOrDefault("type", "content");
            }

            // 퀴즈 챕터는 진행률 계산에서 제외
            if ("quiz".equals(chapterType)) {
                // 퀴즈 챕터는 섹션 수 0으로 설정하고 cumulativeSections에 포함하지 않음
                result.add(ChapterProgressDto.builder()
                        .chapterId(chapterId)
                        .chapterTitle(chapterTitle)
                        .chapterType(chapterType)
                        .chapterNumber(i + 1)
                        .totalSections(0)
                        .completedSections(0)
                        .progressPercentage(0.0)
                        .isCompleted(false)
                        .build());
                continue; // 다음 챕터로
            }

            // Section 수 계산 (구조에 맞게 자동 판별)
            int totalSections = calculateSectionsFromChapter(chapter);

            // 현재 진행 상황에 따른 완료된 섹션 계산
            int completedSections;
            boolean isCompleted;

            if (progress == null) {
                completedSections = 0;
                isCompleted = false;
            } else {
                int chapterStartPage = cumulativeSections + 1;
                int chapterEndPage = cumulativeSections + totalSections;

                if (contentCurrentPage > chapterEndPage) {
                    // 이 챕터는 완료됨
                    completedSections = totalSections;
                    isCompleted = true;
                } else if (contentCurrentPage >= chapterStartPage) {
                    // 현재 이 챕터를 학습 중
                    completedSections = contentCurrentPage - chapterStartPage + 1;
                    isCompleted = false;
                } else {
                    // 아직 시작하지 않음
                    completedSections = 0;
                    isCompleted = false;
                }
            }

            double progressPercentage = totalSections > 0
                    ? (double) completedSections / totalSections * 100.0
                    : 0.0;

            result.add(ChapterProgressDto.builder()
                    .chapterId(chapterId)
                    .chapterTitle(chapterTitle)
                    .chapterType(chapterType)
                    .chapterNumber(i + 1)
                    .totalSections(totalSections)
                    .completedSections(completedSections)
                    .progressPercentage(Math.round(progressPercentage * 100.0) / 100.0)
                    .isCompleted(isCompleted)
                    .build());

            cumulativeSections += totalSections;
        }

        return result;
    }

    /**
     * 챕터에서 섹션 수 계산
     * 두 가지 JSON 구조를 모두 지원:
     * 1. 이전 구조: titles, s_titles, ss_titles, concept_checks
     * 2. 새로운 구조: 단순 chapters 배열 (각 chapter = 1 섹션)
     */
    private int calculateSectionsFromChapter(Map<String, Object> chapter) {
        // 구조 판별: "index" 키가 있으면 이전 구조, "id" 키가 있으면 새로운 구조
        if (chapter.containsKey("index") && chapter.containsKey("index_title")) {
            // 이전 구조 (parsedData.data)
            return calculateSectionsFromOldStructure(chapter);
        } else if (chapter.containsKey("id") && chapter.containsKey("title")) {
            // 새로운 구조 (chapters)
            return calculateSectionsFromNewStructure(chapter);
        } else {
            log.warn("알 수 없는 챕터 구조: keys={}", chapter.keySet());
            return 1; // 최소 1 섹션
        }
    }

    /**
     * 이전 JSON 구조에서 섹션 수 계산
     * titles, s_titles, ss_titles, concept_checks를 모두 카운팅
     */
    private int calculateSectionsFromOldStructure(Map<String, Object> chapter) {
        int sectionCount = 0;

        String chapterId = (String) chapter.get("index");
        String chapterTitle = (String) chapter.get("index_title");

        // 1. titles 배열 처리
        List<Map<String, Object>> titles = (List<Map<String, Object>>) chapter.get("titles");
        if (titles != null) {
            log.debug("챕터 [{}] titles 개수: {}", chapterId, titles.size());

            for (int i = 0; i < titles.size(); i++) {
                Map<String, Object> title = titles.get(i);
                int titleSections = 0;

                // title 자체도 하나의 섹션
                sectionCount++;
                titleSections++;

                // s_titles 배열 처리
                List<Map<String, Object>> sTitles = (List<Map<String, Object>>) title.get("s_titles");
                if (sTitles != null) {
                    for (Map<String, Object> sTitle : sTitles) {
                        // s_title도 하나의 섹션
                        sectionCount++;
                        titleSections++;

                        // ss_titles 배열 처리
                        List<Map<String, Object>> ssTitles = (List<Map<String, Object>>) sTitle.get("ss_titles");
                        if (ssTitles != null) {
                            // 각 ss_title도 하나의 섹션
                            sectionCount += ssTitles.size();
                            titleSections += ssTitles.size();
                        }
                    }
                }

                log.debug("  - title[{}]: {} → {} 섹션", i, title.get("title"), titleSections);
            }
        }

        // 2. concept_checks 배열 처리 (퀴즈는 진행률에서 제외)
        List<Map<String, Object>> conceptChecks = (List<Map<String, Object>>) chapter.get("concept_checks");
        boolean hasConceptChecks = conceptChecks != null && !conceptChecks.isEmpty();
        if (hasConceptChecks) {
            log.debug("챕터 [{}] concept_checks 개수: {} (진행률 계산에서 제외)", chapterId, conceptChecks.size());
            // 퀴즈는 진행률 계산에서 제외하므로 카운팅하지 않음
            // sectionCount += conceptChecks.size();
        }

        // 퀴즈만 있고 콘텐츠가 없는 챕터는 0 섹션 반환
        if (sectionCount == 0 && hasConceptChecks) {
            log.info("챕터 [{}] {} - 0 섹션 (퀴즈 전용 챕터, 진행률 제외)", chapterId, chapterTitle);
            return 0;
        }

        log.info("챕터 [{}] {} - 총 {} 섹션 (이전 구조)", chapterId, chapterTitle, sectionCount);

        // 콘텐츠가 있는 경우 최소 1개 섹션 보장
        return Math.max(1, sectionCount);
    }

    /**
     * 새로운 JSON 구조에서 섹션 수 계산
     * 각 chapter가 1개의 섹션 (퀴즈는 제외)
     */
    private int calculateSectionsFromNewStructure(Map<String, Object> chapter) {
        String chapterId = (String) chapter.get("id");
        String chapterTitle = (String) chapter.get("title");
        String chapterType = (String) chapter.get("type");

        // 퀴즈 챕터는 진행률 계산에서 제외
        if ("quiz".equals(chapterType)) {
            log.info("챕터 [{}] {} (type: quiz) - 0 섹션 (퀴즈 제외)", chapterId, chapterTitle);
            return 0;
        }

        log.info("챕터 [{}] {} (type: {}) - 1 섹션 (새로운 구조)", chapterId, chapterTitle, chapterType);

        // 새로운 구조에서는 각 chapter가 1개의 섹션
        return 1;
    }

    /**
     * 학습 진행률 업데이트
     */
    @Transactional
    public UpdateProgressResponse updateProgress(Long studentId, Long materialId, Integer currentPage, Integer totalPages) {
        policy.studentMaterial(studentId, materialId);
        if (currentPage == null || currentPage < 0 || currentPage > 100000
            || (totalPages != null && (totalPages < 1 || totalPages > 100000 || currentPage > totalPages)))
            throw A704.DODREAM.authorization.AuthorizationPolicy.invalid();
        // 1. 학생 조회
        User student = userRepository.findById(studentId)
                .orElseThrow(() -> new CustomException(ErrorCode.USER_NOT_FOUND));

        // 2. 공유 권한 확인
        MaterialShare share = materialShareRepository.findByStudentIdAndMaterialId(studentId, materialId)
                .orElseThrow(() -> new CustomException(ErrorCode.MATERIAL_NOT_FOUND));

        Material material = share.getMaterial();

        StudentMaterialProgress progress = progressRepository
                .findByStudentIdAndMaterialId(studentId, materialId)
                .orElse(null);

        // An omitted total is not a request to shrink a previously known document length.
        if (totalPages == null) {
            int previousTotal = progress != null && progress.getTotalPages() != null ? progress.getTotalPages() : 0;
            totalPages = Math.max(1,Math.max(previousTotal,currentPage));
        }

        if (progress == null) {
            // 새로운 진행 기록 생성
            progress = StudentMaterialProgress.builder()
                    .student(student)
                    .material(material)
                    .currentPage(currentPage)  // 앱이 보낸 값 그대로 저장
                    .totalPages(totalPages)    // 앱이 보낸 값 그대로 저장
                    .progressPercentage(0)
                    .build();
        }

        // 5. totalPages 업데이트 (필요한 경우)
        if (progress.getTotalPages() == null || !totalPages.equals(progress.getTotalPages())) {
            log.info("totalPages 업데이트: {} → {}", progress.getTotalPages(), totalPages);
            progress.updateTotalPages(totalPages);
        }
        
        // 6. 진행률 업데이트 (앱이 보낸 currentPage 그대로 사용)
        progress.updateProgress(currentPage);

        // 7. 저장
        StudentMaterialProgress saved = progressRepository.save(progress);
        
        // 8. 실제 진행률 계산
        int calculatedPercentage = 0;
        if (saved.getTotalPages() != null && saved.getTotalPages() > 0) {
            calculatedPercentage = (int)((saved.getCurrentPage() * 100.0) / saved.getTotalPages());
        }
        
        log.info("진행률 저장 완료: currentPage={}/{} = {}%", 
                saved.getCurrentPage(), saved.getTotalPages(), calculatedPercentage);

        // 9. 응답 생성
        String message = saved.getCompletedAt() != null 
                ? "🎉 축하합니다! 모든 학습을 완료했습니다!"
                : String.format("진행률 업데이트 완료 (%d%%)", calculatedPercentage);

        return UpdateProgressResponse.builder()
                .studentId(saved.getStudent().getId())
                .materialId(saved.getMaterial().getId())
                .currentPage(saved.getCurrentPage())
                .totalPages(saved.getTotalPages())
                .progressPercentage(calculatedPercentage)
                .isCompleted(saved.getCompletedAt() != null)
                .lastAccessedAt(saved.getLastAccessedAt())
                .completedAt(saved.getCompletedAt())
                .message(message)
                .build();
    }

    /**
     * JSON에서 chapters 추출 (3가지 패턴 모두 지원)
     * 패턴 1: parsedData.data (이전 구조)
     * 패턴 2: data (이전 구조)
     * 패턴 3: chapters (새로운 구조 - EC2)
     */
    private List<Map<String, Object>> extractChapters(Map<String, Object> jsonData) {
        log.info("=== extractChapters 시작 ===");
        log.info("JSON 최상위 keys: {}", jsonData.keySet());

        // 패턴 1: parsedData.data 구조 (이전)
        Map<String, Object> parsedData = (Map<String, Object>) jsonData.get("parsedData");
        if (parsedData != null) {
            log.info("패턴 1 시도: parsedData 존재, keys: {}", parsedData.keySet());
            List<Map<String, Object>> chapters = (List<Map<String, Object>>) parsedData.get("data");
            if (chapters != null) {
                log.info("✅ 패턴 1 성공: parsedData.data에서 {} 개의 챕터 발견", chapters.size());
                return chapters;
            }
        }

        // 패턴 2: 직접 data 구조 (이전)
        List<Map<String, Object>> chapters = (List<Map<String, Object>>) jsonData.get("data");
        if (chapters != null) {
            log.info("✅ 패턴 2 성공: data에서 {} 개의 챕터 발견", chapters.size());
            return chapters;
        }

        // 패턴 3: 직접 chapters 구조 (새로운 - EC2)
        chapters = (List<Map<String, Object>>) jsonData.get("chapters");
        if (chapters != null) {
            log.info("✅ 패턴 3 성공: chapters에서 {} 개의 챕터 발견 (새로운 JSON 구조)", chapters.size());
            return chapters;
        }

        log.error("❌ 모든 패턴 실패: chapters를 찾을 수 없습니다.");
        throw new CustomException(ErrorCode.INVALID_JSON_STRUCTURE);
    }

    /**
     * 총 섹션 수 계산 (퀴즈 제외)
     */
    private int calculateTotalSections(List<Map<String, Object>> chapters) {
        int total = 0;
        for (Map<String, Object> chapter : chapters) {
            // calculateSectionsFromChapter가 퀴즈일 경우 0을 반환하도록 되어 있음
            total += calculateSectionsFromChapter(chapter);
        }
        log.info("전체 섹션 수 계산 완료: {} 섹션 (퀴즈 제외)", total);
        return total;
    }

    /**
     * 현재 학습 중인 챕터 찾기 (퀴즈 제외)
     */
    private ChapterProgressDto findCurrentChapter(List<ChapterProgressDto> chapterProgress) {
        // 완료되지 않은 첫 번째 콘텐츠 챕터를 현재 챕터로 간주 (퀴즈 제외)
        for (ChapterProgressDto chapter : chapterProgress) {
            if (!"quiz".equals(chapter.getChapterType()) && !chapter.isCompleted()) {
                return chapter;
            }
        }

        // 모든 콘텐츠 챕터가 완료된 경우 마지막 콘텐츠 챕터 반환
        for (int i = chapterProgress.size() - 1; i >= 0; i--) {
            ChapterProgressDto chapter = chapterProgress.get(i);
            if (!"quiz".equals(chapter.getChapterType())) {
                return chapter;
            }
        }

        // 콘텐츠 챕터가 없으면 null
        return null;
    }

    /**
     * 특정 학생의 모든 교재에 대한 평균 진행률 조회
     */
    public AverageProgressResponse getAverageProgress(Long studentId, Long actorId) {
        policy.historySubject(actorId, studentId);
        // 1. 학생 조회
        User student = userRepository.findById(studentId)
                .orElseThrow(() -> new CustomException(ErrorCode.USER_NOT_FOUND));

        // 2. 모든 진행률 리포트 조회
        List<ProgressReportResponse> reports = getAllProgressReports(studentId, actorId);

        // 3. 통계 계산
        int totalMaterials = reports.size();
        int completedMaterials = 0;
        int inProgressMaterials = 0;
        int notStartedMaterials = 0;
        double totalProgress = 0.0;

        for (ProgressReportResponse report : reports) {
            double progress = report.getOverallProgressPercentage();
            totalProgress += progress;

            if (report.getCompletedAt() != null || progress >= 100.0) {
                // 완료한 교재
                completedMaterials++;
            } else if (progress > 0.0) {
                // 학습 중인 교재
                inProgressMaterials++;
            } else {
                // 시작하지 않은 교재
                notStartedMaterials++;
            }
        }

        // 4. 평균 진행률 계산
        double averageProgress = totalMaterials > 0
                ? totalProgress / totalMaterials
                : 0.0;

        // 5. 응답 생성
        return AverageProgressResponse.builder()
                .studentId(student.getId())
                .studentName(student.getName())
                .totalMaterials(totalMaterials)
                .averageProgressPercentage(Math.round(averageProgress * 100.0) / 100.0)
                .completedMaterials(completedMaterials)
                .inProgressMaterials(inProgressMaterials)
                .notStartedMaterials(notStartedMaterials)
                .build();
    }
}

