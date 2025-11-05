package A704.DODREAM.material.repository;

import A704.DODREAM.material.entity.MaterialShare;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Set;

@Repository
public interface MaterialShareRepository extends JpaRepository<MaterialShare, Long> {
    @Query("SELECT ms.student.id FROM MaterialShare ms " +
            "WHERE ms.material.id = :materialId AND ms.student.id IN :studentIds")
    Set<Long> findStudentIdsByMaterialIdAndStudentIdIn(Long materialId, Set<Long> studentIds
    );

    // 앱에서 공유받은 자료 목록 조회 (학생)
    @Query("SELECT ms FROM MaterialShare ms " +
            "JOIN FETCH ms.material m " +
            "JOIN FETCH ms.teacher t " +
            "WHERE ms.student.id = :studentId " +
            "ORDER BY ms.sharedAt DESC")
    List<MaterialShare> findByStudentId(Long studentId);

    // 웹에서 공유한 자료 목록을 학생별로 조회 (선생님)
    @Query("SELECT ms FROM MaterialShare ms " +
            "JOIN FETCH ms.material m " +
            "JOIN FETCH ms.teacher t " +
            "WHERE ms.student.id = :studentId " +
            "AND ms.teacher.id = :teacherId " +
            "ORDER BY ms.sharedAt DESC")
    List<MaterialShare> findByStudentIdAndTeacherId(Long studentId, Long teacherId);

    //웹에서 공유한 자료 목록을 반별로 조회 (선생님)
    @Query("SELECT ms FROM MaterialShare ms " +
            "JOIN FETCH ms.material m " +
            "JOIN FETCH ms.teacher t " +
            "WHERE ms.sharedGrade = :gradeLevel " +
            "AND ms.sharedClass = :classNumber " +
            "AND ms.sharedYear = :year " +
            "AND ms.teacher.id = :teacherId " +
            "AND ms.id IN (" +
            "  SELECT MAX(ms2.id) FROM MaterialShare ms2 " +
            "  WHERE ms2.sharedGrade = :gradeLevel " +
            "  AND ms2.sharedClass = :classNumber " +
            "  AND ms2.sharedYear = :year " +
            "  AND ms2.teacher.id = :teacherId " +
            "  GROUP BY ms2.material.id" +
            ") " +
            "ORDER BY ms.sharedAt DESC")
    List<MaterialShare> findByClassInfoAndTeacherId(
            Integer gradeLevel,
            Integer classNumber,
            Integer year,
            Long teacherId
    );
}
