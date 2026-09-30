package A704.DODREAM.demo;

import A704.DODREAM.auth.entity.PasswordCredential;
import A704.DODREAM.auth.exception.AuthException;
import A704.DODREAM.authorization.AuthorizationPolicy;
import A704.DODREAM.file.entity.UploadedFile;
import A704.DODREAM.indexing.IndexingStore;
import A704.DODREAM.material.entity.*;
import A704.DODREAM.material.enums.ShareType;
import A704.DODREAM.user.entity.*;
import jakarta.persistence.*;
import java.time.Instant;
import java.util.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service @Profile("local") @ConditionalOnProperty(name="LOCAL_DEMO_ENABLED",havingValue="true")
@Transactional
public class LocalDemoStore {
    private final EntityManager em;
    private final AuthorizationPolicy policy;
    private final IndexingStore indexing;
    public LocalDemoStore(EntityManager em,AuthorizationPolicy policy,IndexingStore indexing) {this.em=em;this.policy=policy;this.indexing=indexing;}
    public void initialize(String password,PasswordEncoder encoder) {
        if(em.find(DemoCatalog.class,DemoManifest.VERSION)!=null) return;
        var school=save(School.create("DO:DREAM 웹 체험 합성 학교"));
        var classroom=save(Classroom.builder().school(school).year(2026).gradeLevel(3).classNumber(1).build());
        var teacher=save(User.create("웹 체험 합성 교사",Role.TEACHER));
        var profile=save(TeacherProfile.create(teacher,"DEMO-WEB-V1"));
        save(ClassroomTeacher.builder().teacher(profile).classroom(classroom).build());
        save(PasswordCredential.create(teacher,DemoManifest.TEACHER_EMAIL,encoder.encode(password)));
        save(new DemoCatalog(DemoManifest.VERSION,teacher.getId(),classroom.getId()));
    }
    public record SampleView(String key,long fileId,Long materialId) {}
    public record CatalogView(long teacherId,long classroomId,int visitors,List<SampleView> samples) {}
    public CatalogView catalog() {
        var c=catalog(false);
        return new CatalogView(c.teacherId,c.classroomId,c.visitorCount,
            em.createQuery("select s from DemoSample s where s.fixtureVersion=:version order by s.sampleKey",DemoSample.class)
                .setParameter("version",DemoManifest.VERSION).getResultList().stream().map(s->new SampleView(s.sampleKey,s.fileId,s.materialId)).toList());
    }
    public List<SampleView> reservePreparation(long actor) {
        var c=catalog(true); owner(actor,c);
        if(c.preparingUntil!=null && c.preparingUntil.isAfter(Instant.now())) throw failure(409,"DEMO_PREPARATION_IN_PROGRESS");
        c.preparingUntil=Instant.now().plusSeconds(120);
        var result=new ArrayList<SampleView>();
        for(var sample:DemoManifest.SAMPLES) {
            var row=em.find(DemoSample.class,sample.key());
            if(row==null) {
                var file=save(UploadedFile.builder().uploaderId(actor).originalFileName("demo-"+sample.key()+".json")
                    .s3Bucket("local-synthetic-fixtures").contentType("application/json").fileType("application/json").fileSize(0L).build());
                row=save(new DemoSample(sample.key(),DemoManifest.VERSION,file.getId()));
            }
            policy.ownedFile(actor,row.fileId);
            if(row.materialId==null) {
                var published=em.createQuery("select m from Material m where m.uploadedFile.id=:id",Material.class).setParameter("id",row.fileId).getResultList();
                if(!published.isEmpty()) row.materialId=policy.owned(actor,published.get(0).getId()).getId();
            }
            result.add(new SampleView(row.sampleKey,row.fileId,row.materialId));
        }
        return result;
    }
    public void prepared(long actor,String key,long materialId) {
        var c=catalog(true);owner(actor,c);var sample=em.find(DemoSample.class,key,LockModeType.PESSIMISTIC_WRITE);
        var material=policy.owned(actor,materialId);
        if(sample==null || material.getUploadedFile().getId()!=sample.fileId) throw AuthorizationPolicy.invalid();
        sample.materialId=materialId;
    }
    public void finishPreparation(long actor) {var c=catalog(true);owner(actor,c);c.preparingUntil=null;}
    /** Global catalog lock bounds the number of committed visitors even across simultaneous processes. */
    public User start(String hash,int maximum) {
        var c=catalog(true);
        var visitor=em.find(DemoVisitor.class,hash,LockModeType.PESSIMISTIC_WRITE);
        if(visitor!=null && visitor.startingUntil!=null && visitor.startingUntil.isAfter(Instant.now())) throw failure(409,"DEMO_START_IN_PROGRESS");
        var samples=catalog().samples();
        if(samples.size()!=DemoManifest.SAMPLES.size()) throw failure(503,"DEMO_NOT_READY");
        if(samples.stream().anyMatch(sample->sample.materialId()==null)) throw failure(503,"DEMO_NOT_READY");
        var readiness=indexing.materialSummaries(c.teacherId,samples.stream().map(SampleView::materialId).toList());
        if(readiness.values().stream().anyMatch(status->!status.readable())) throw failure(503,"DEMO_NOT_READY");
        if(visitor==null) {
            if(c.visitorCount>=maximum) throw failure(429,"DEMO_CAPACITY_REACHED");
            var classroom=em.find(Classroom.class,c.classroomId);
            policy.classroom(c.teacherId,c.classroomId);
            var user=save(User.create("체험 학생 "+(c.visitorCount+1),Role.STUDENT));
            save(StudentProfile.create(user,classroom.getSchool().getName(),"DEMO-V1-"+UUID.randomUUID(),classroom,"UNSPECIFIED"));
            for(var sample:samples) {
                var material=policy.owned(c.teacherId,sample.materialId());
                save(MaterialShare.builder().material(material).teacher(em.find(User.class,c.teacherId)).student(user).classroom(classroom).shareType(ShareType.INDIVIDUAL).build());
            }
            visitor=save(new DemoVisitor(hash,user,DemoManifest.VERSION));c.visitorCount++;
        }
        policy.student(visitor.user.getId());
        for(var sample:samples) policy.studentMaterial(visitor.user.getId(),sample.materialId());
        visitor.startingUntil=Instant.now().plusSeconds(30);
        return visitor.user;
    }
    public void issued(String hash) {
        var visitor=em.find(DemoVisitor.class,hash,LockModeType.PESSIMISTIC_WRITE);
        if(visitor!=null) visitor.startingUntil=Instant.now().plusSeconds(3);
    }
    public Map<String,Long> counts(long actor) {
        owner(actor);
        long files=count("select count(*) from local_demo_samples where fixture_version=:version");
        long materials=count("select count(*) from local_demo_samples where fixture_version=:version and material_id is not null");
        long quizzes=count("select count(*) from quizzes q join local_demo_samples s on s.material_id=q.material_id where s.fixture_version=:version");
        long jobs=count("select count(*) from index_jobs j join index_resources r on r.id=j.resource_pk join local_demo_samples s on (r.resource_kind='MATERIAL' and r.resource_id=s.material_id) or (r.resource_kind='PDF' and r.resource_id=s.file_id) where s.fixture_version=:version");
        return Map.of("files",files,"materials",materials,"quizzes",quizzes,"logicalJobs",jobs);
    }
    private long count(String query) {return ((Number)em.createNativeQuery(query).setParameter("version",DemoManifest.VERSION).getSingleResult()).longValue();}
    public boolean isDemo(long user) {return em.createQuery("select count(v) from DemoVisitor v where v.user.id=:user",Long.class).setParameter("user",user).getSingleResult()>0;}
    public void owner(long actor) {owner(actor,catalog(false));}
    private void owner(long actor,DemoCatalog c) {policy.teacher(actor);if(actor!=c.teacherId)throw AuthorizationPolicy.hidden();}
    private DemoCatalog catalog(boolean lock) {
        var c=lock?em.find(DemoCatalog.class,DemoManifest.VERSION,LockModeType.PESSIMISTIC_WRITE):em.find(DemoCatalog.class,DemoManifest.VERSION);
        if(c==null)throw failure(503,"DEMO_NOT_READY");return c;
    }
    private <T> T save(T value) {em.persist(value);return value;}
    static AuthException failure(int status,String code) {return new AuthException(HttpStatus.valueOf(status),code,code);}
}
