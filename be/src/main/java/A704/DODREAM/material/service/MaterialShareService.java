package A704.DODREAM.material.service;

import A704.DODREAM.material.dto.MaterialShareRequest;
import A704.DODREAM.material.dto.MaterialShareResponse;
import A704.DODREAM.material.entity.Material;
import A704.DODREAM.material.entity.MaterialShare;
import A704.DODREAM.material.repository.MaterialRepository;
import A704.DODREAM.material.repository.MaterialShareRepository;
import A704.DODREAM.user.entity.User;
import A704.DODREAM.user.repository.UserRepository;
import jakarta.transaction.Transactional;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Transactional
public class MaterialShareService {
    private final MaterialShareRepository materialShareRepository;
    private final MaterialRepository materialRepository;
    private final UserRepository userRepository;

    //자료 공유
    @Transactional
    public MaterialShareResponse shareMaterial(MaterialShareRequest request){

        //자료 조회
        Material material = materialRepository.findById(request.getMaterialId())
                .orElseThrow(() -> new IllegalArgumentException("자료를 찾을 수 없습니다."));

        //선생님 조회
        User teacher = userRepository.findById(request.getTeacherId())
                .orElseThrow(() -> new IllegalArgumentException("선생님을 찾을 수 없습니다."));

        //학생 조회
        List<User> students = userRepository.findAllById(request.getStudentIds());
        Map<Long, User> studentMap = students.stream()
                .collect(Collectors.toMap(User::getId, Function.identity()));

        //이미 공유된 학생 조회
        Set<Long> sharedIds = materialShareRepository.findStudentIdsByMaterialIdAndStudentIdIn(material.getId(), request.getStudentIds());

        List<MaterialShare> sharesToSave = new ArrayList<>();
        List<MaterialShareResponse.ShareResult> results = new ArrayList<>();

        for (Long studentId : request.getStudentIds()) {
            User student = studentMap.get(studentId);

            // 학생을 찾을 수 없는 경우
            if (student == null) {
                results.add(MaterialShareResponse.ShareResult.builder()
                        .studentId(studentId)
                        .studentName("알 수 없음")
                        .success(false)
                        .message("학생을 찾을 수 없습니다")
                        .build());
                continue;
            }

            // 이미 공유된 경우
            if (sharedIds.contains(studentId)) {
                results.add(MaterialShareResponse.ShareResult.builder()
                        .studentId(studentId)
                        .studentName(student.getName())
                        .success(false)
                        .message("이미 공유된 자료입니다")
                        .build());
                continue;
            }

            // 공유할 데이터 추가
            MaterialShare share = MaterialShare.builder()
                    .material(material)
                    .teacher(teacher)
                    .student(student)
                    .shareMessage(request.getShareMessage())
                    .build();
            sharesToSave.add(share);
        }

        List<MaterialShare> savedShares = materialShareRepository.saveAll(sharesToSave);

        for(MaterialShare share : savedShares){

            results.add(MaterialShareResponse.ShareResult.builder()
                    .shareId(share.getId())
                    .studentId(share.getStudent().getId())
                    .studentName(share.getStudent().getName())
                    .success(true)
                    .message("공유 완료")
                    .sharedAt(share.getSharedAt())
                    .build());
        }

        long successCount = results.stream().filter(MaterialShareResponse.ShareResult::isSuccess).count();

        return MaterialShareResponse.builder()
                .materialId(material.getId())
                .materialTitle(material.getTitle())
                .teacherId(teacher.getId())
                .teacherName(teacher.getName())
                .shareMessage(request.getShareMessage())
                .totalShared((int) successCount)
                .results(results)
                .message(String.format("%d명의 학생에게 공유되었습니다", successCount))
                .build();
    }

}
