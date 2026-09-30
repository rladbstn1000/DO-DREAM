package A704.DODREAM.demo;

import A704.DODREAM.authorization.AuthorizationPolicy;
import A704.DODREAM.file.entity.UploadedFile;
import A704.DODREAM.indexing.IndexingFailure;
import A704.DODREAM.material.entity.*;
import A704.DODREAM.material.enums.ShareType;
import A704.DODREAM.quiz.entity.Quiz;
import A704.DODREAM.user.entity.*;
import jakarta.persistence.*;
import java.time.Instant;
import java.util.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

/** Short transactions only. Catalog locking bounds this fixture to four new materials. */
@Service @Profile("local") @ConditionalOnProperty(name={"LOCAL_DEMO_ENABLED","LOCAL_PHASE5_ENABLED"},havingValue="true")
@Transactional(propagation=Propagation.REQUIRES_NEW,timeout=8)
public class Phase5Store {
    private final EntityManager em;
    private final AuthorizationPolicy policy;
    private final JdbcTemplate db;
    public Phase5Store(EntityManager em,AuthorizationPolicy policy,JdbcTemplate db){this.em=em;this.policy=policy;this.db=db;}
    public record Reserved(String key,long fileId,Long materialId) {}
    public record Prepared(String material_key,long material_id,List<Long> user_ids,long source_revision,String source_hash,
        String spec,String job_id,Map<String,Long> quiz_mapping) {}
    private DemoCatalog owner(long actor,boolean lock) {
        policy.teacher(actor);
        var c=lock?em.find(DemoCatalog.class,DemoManifest.VERSION,LockModeType.PESSIMISTIC_WRITE):em.find(DemoCatalog.class,DemoManifest.VERSION);
        if(c==null || c.teacherId!=actor)throw AuthorizationPolicy.hidden();
        policy.classroom(actor,c.classroomId);return c;
    }
    private void student(Long studentId,DemoCatalog c) {
        if(studentId==null)return;
        policy.student(studentId);
        long visitors=em.createQuery("select count(v) from DemoVisitor v where v.user.id=:id and v.fixtureVersion=:version",Long.class)
            .setParameter("id",studentId).setParameter("version",DemoManifest.VERSION).getSingleResult();
        long profiles=em.createQuery("select count(s) from StudentProfile s where s.user.id=:id and s.classroom.id=:classroom",Long.class)
            .setParameter("id",studentId).setParameter("classroom",c.classroomId).getSingleResult();
        if(visitors!=1 || profiles!=1)throw AuthorizationPolicy.hidden();
    }
    public List<Reserved> reserve(long actor,Long studentId) {
        var c=owner(actor,true);student(studentId,c);
        if(c.preparingUntil!=null && c.preparingUntil.isAfter(Instant.now()))throw new IndexingFailure(409,"DEMO_PREPARATION_IN_PROGRESS");
        c.preparingUntil=Instant.now().plusSeconds(120);
        var rows=new ArrayList<Reserved>();
        for(var sample:Phase5Manifest.SAMPLES) {
            var row=em.find(DemoSample.class,sample.sampleKey());
            if(row==null) {
                var file=UploadedFile.builder().uploaderId(actor).originalFileName(sample.sampleKey()+".json")
                    .s3Bucket("local-synthetic-fixtures").contentType("application/json").fileType("application/json").fileSize(0L).build();
                em.persist(file);row=new DemoSample(sample.sampleKey(),Phase5Manifest.VERSION,file.getId());em.persist(row);
            }
            if(!Phase5Manifest.VERSION.equals(row.fixtureVersion))throw new IndexingFailure(409,"PHASE5_FIXTURE_CONFLICT");
            policy.ownedFile(actor,row.fileId);
            if(row.materialId==null) {
                var published=em.createQuery("select m from Material m where m.uploadedFile.id=:id",Material.class).setParameter("id",row.fileId).getResultList();
                if(published.size()>1)throw new IndexingFailure(409,"PHASE5_FIXTURE_CONFLICT");
                if(!published.isEmpty())row.materialId=policy.owned(actor,published.get(0).getId()).getId();
            }
            if(row.materialId!=null)validate(actor,row.materialId,sample);
            rows.add(new Reserved(sample.key(),row.fileId,row.materialId));
        }
        return rows;
    }
    public void prepared(long actor,Phase5Manifest.Sample sample,long id) {
        owner(actor,true);var row=em.find(DemoSample.class,sample.sampleKey(),LockModeType.PESSIMISTIC_WRITE);
        if(row==null || !Phase5Manifest.VERSION.equals(row.fixtureVersion) || policy.owned(actor,id).getUploadedFile().getId()!=row.fileId)
            throw AuthorizationPolicy.hidden();
        if(row.materialId!=null && row.materialId!=id)throw new IndexingFailure(409,"PHASE5_FIXTURE_CONFLICT");
        validate(actor,id,sample);row.materialId=id;
    }
    private List<Quiz> validate(long actor,long id,Phase5Manifest.Sample sample) {
        var material=policy.owned(actor,id);
        var hashes=db.queryForList("SELECT current_source_hash FROM index_resources WHERE resource_kind='MATERIAL' AND resource_id=?",String.class,id);
        if(!sample.title().equals(material.getTitle()) || hashes.size()!=1 || !sample.sourceHash().equals(hashes.get(0)))
            throw new IndexingFailure(409,"PHASE5_SOURCE_CHANGED");
        var quizzes=em.createQuery("select q from Quiz q where q.material.id=:id order by q.questionNumber,q.id",Quiz.class).setParameter("id",id).getResultList();
        if(quizzes.size()!=sample.questions().size())throw new IndexingFailure(409,"PHASE5_QUIZZES_CHANGED");
        for(int i=0;i<quizzes.size();i++) {var q=quizzes.get(i);var expected=sample.questions().get(i);
            if(q.getQuestionNumber()!=i+1 || !q.getContent().equals(expected.question()) || !q.getCorrectAnswer().equals(expected.answer())
                || !Objects.equals(q.getChapterReference(),expected.chapter()) || !"SHORT_ANSWER".equals(q.getQuestionType()))
                throw new IndexingFailure(409,"PHASE5_QUIZZES_CHANGED");}
        return quizzes;
    }
    public boolean hasLiveJob(long actor,long id,Phase5Manifest.Sample sample) {
        owner(actor,false);validate(actor,id,sample);
        var rows=db.queryForList("SELECT j.id,r.latest_job_id FROM index_resources r JOIN index_jobs j ON j.resource_pk=r.id AND j.source_revision=r.source_revision WHERE r.resource_kind='MATERIAL' AND r.resource_id=? AND j.index_spec=?",id,Phase5Manifest.SPEC);
        if(rows.isEmpty())return false;
        if(rows.size()!=1 || !Objects.equals(rows.get(0).get("id"),rows.get(0).get("latest_job_id")))throw new IndexingFailure(409,"PHASE5_SOURCE_CHANGED");
        return true;
    }
    public Prepared result(long actor,Long studentId,long id,Phase5Manifest.Sample sample) {
        var c=owner(actor,true);student(studentId,c);var quizzes=validate(actor,id,sample);
        var rows=db.queryForList("SELECT j.job_id,j.source_revision,j.source_hash,j.index_spec FROM index_resources r JOIN index_jobs j ON j.id=r.latest_job_id AND j.resource_pk=r.id AND j.source_revision=r.source_revision WHERE r.resource_kind='MATERIAL' AND r.resource_id=? AND j.index_spec=?",id,Phase5Manifest.SPEC);
        if(rows.size()!=1)throw new IndexingFailure(409,"PHASE5_LIVE_JOB_MISSING");
        var row=rows.get(0);var users=new ArrayList<Long>();users.add(actor);
        if(studentId!=null) {
            users.add(studentId);
            long shared=em.createQuery("select count(s) from MaterialShare s where s.material.id=:material and s.student.id=:student",Long.class)
                .setParameter("material",id).setParameter("student",studentId).getSingleResult();
            if(shared==0)em.persist(MaterialShare.builder().material(policy.owned(actor,id)).teacher(em.find(User.class,actor))
                .student(em.find(User.class,studentId)).classroom(em.find(Classroom.class,c.classroomId)).shareType(ShareType.INDIVIDUAL).build());
        }
        var mapping=new LinkedHashMap<String,Long>();
        for(int i=0;i<quizzes.size();i++) {String key=sample.questions().get(i).caseId();mapping.put(key.isBlank()?"smoke-"+(i+1):key,quizzes.get(i).getId());}
        return new Prepared(sample.key(),id,List.copyOf(users),((Number)row.get("source_revision")).longValue(),
            (String)row.get("source_hash"),(String)row.get("index_spec"),(String)row.get("job_id"),Map.copyOf(mapping));
    }
    public void finish(long actor){owner(actor,true).preparingUntil=null;}
}
