package A704.DODREAM.demo;

import jakarta.persistence.*;
import java.time.Instant;

/** Local-only records are additive; no existing fixture is repurposed. */
@Entity @Table(name="local_demo_catalogs")
public class DemoCatalog {
    @Id @Column(length=40) String version;
    @Column(nullable=false) long teacherId;
    @Column(nullable=false) long classroomId;
    @Column(nullable=false) int visitorCount;
    Instant preparingUntil;
    protected DemoCatalog() {}
    DemoCatalog(String version,long teacherId,long classroomId) { this.version=version; this.teacherId=teacherId; this.classroomId=classroomId; }
}
