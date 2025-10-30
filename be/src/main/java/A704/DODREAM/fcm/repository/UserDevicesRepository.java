package A704.DODREAM.fcm.repository;

import A704.DODREAM.fcm.entity.UserDevices;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface UserDevicesRepository extends JpaRepository<UserDevices, Long> {

    List<UserDevices> findByUserIdAndIsActiveTrue(Long userId);
//    Optional<UserDe>
}
