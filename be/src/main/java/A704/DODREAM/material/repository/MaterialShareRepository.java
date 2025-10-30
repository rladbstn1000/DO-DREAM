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
    Set<Long> findStudentIdsByMaterialIdAndStudentIdIn(Long materialId, List<Long> studentIds
    );
}
