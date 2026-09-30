package A704.DODREAM.demo;

import jakarta.persistence.*;

@Entity @Table(name="local_demo_samples",uniqueConstraints={@UniqueConstraint(name="uq_demo_sample_file",columnNames="file_id"),@UniqueConstraint(name="uq_demo_sample_material",columnNames="material_id")})
public class DemoSample {
    @Id @Column(length=80) String sampleKey;
    @Column(nullable=false,length=40) String fixtureVersion;
    @Column(name="file_id",nullable=false) long fileId;
    @Column(name="material_id") Long materialId;
    protected DemoSample() {}
    DemoSample(String key,String version,long fileId) {this.sampleKey=key;this.fixtureVersion=version;this.fileId=fileId;}
}
