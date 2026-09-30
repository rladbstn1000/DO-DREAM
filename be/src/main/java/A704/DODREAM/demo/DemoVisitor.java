package A704.DODREAM.demo;

import A704.DODREAM.user.entity.User;
import jakarta.persistence.*;
import java.time.Instant;

@Entity @Table(name="local_demo_visitors")
public class DemoVisitor {
    @Id @Column(length=64) String visitorHash;
    @OneToOne(optional=false) @JoinColumn(name="user_id",nullable=false,unique=true) User user;
    @Column(nullable=false,length=40) String fixtureVersion;
    @Column(nullable=false) Instant createdAt;
    Instant startingUntil;
    protected DemoVisitor() {}
    DemoVisitor(String hash,User user,String version) {visitorHash=hash;this.user=user;fixtureVersion=version;createdAt=Instant.now();}
}
