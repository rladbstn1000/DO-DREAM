package A704.DODREAM.indexing;

import A704.DODREAM.authorization.*;
import A704.DODREAM.file.entity.UploadedFile;
import A704.DODREAM.file.enums.PostStatus;
import A704.DODREAM.file.repository.UploadedFileRepository;
import A704.DODREAM.material.dto.PublishRequest;
import A704.DODREAM.material.entity.Material;
import A704.DODREAM.material.repository.MaterialRepository;
import A704.DODREAM.quiz.service.QuizService;
import jakarta.persistence.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.*;
import org.springframework.transaction.support.*;
import java.time.LocalDateTime;
import java.util.*;

/** Every operation owns a bounded transaction. No object store, HTTP or broker calls occur here. */
@Service
public class IndexingStore {
    private final JdbcTemplate db;
    private final AuthorizationPolicy policy;
    private final EntityManager em;
    private final EntityManagerFactory factory;
    private final UploadedFileRepository files;
    private final MaterialRepository materials;
    private final QuizService quizzes;
    private final IndexingLocalHooks hooks;
    private final TransactionTemplate tx;
    public record FileView(long id,long ownerId,String originalName,String originalKey,String jsonKey,
        String bucket,LocalDateTime parsedAt,boolean synthetic) {}
    public record Publication(long materialId,String filename,String jsonKey,IndexingSummary indexing) {}
    public IndexingStore(JdbcTemplate db,AuthorizationPolicy policy,EntityManager em,EntityManagerFactory factory,
        UploadedFileRepository files,MaterialRepository materials,QuizService quizzes,
        PlatformTransactionManager manager,IndexingLocalHooks hooks) {
        this.db=db; this.policy=policy; this.em=em; this.factory=factory; this.files=files;
        this.materials=materials; this.quizzes=quizzes; this.hooks=hooks;
        tx=new TransactionTemplate(manager); tx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
        tx.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED); tx.setTimeout(8);
    }
    private <T> T transaction(TransactionCallback<T> callback) {
        // As in grading, the short transaction owns/closes its EntityManager despite request OSIV.
        Object holder=null;
        if(!TransactionSynchronizationManager.isActualTransactionActive())
            holder=TransactionSynchronizationManager.unbindResourceIfPossible(factory);
        try { return tx.execute(s->{em.clear(); return callback.doInTransaction(s);}); }
        catch(org.springframework.dao.DataAccessException unavailable) { throw new IndexingFailure(503,"INDEXING_DATABASE_UNAVAILABLE"); }
        finally { if(holder!=null) TransactionSynchronizationManager.bindResource(factory,holder); }
    }
    public void teacher(long actor) { transaction(s->{policy.teacher(actor); return null;}); }
    public long createUploadedFile(long actor,UploadedFile file) {
        return transaction(s->{policy.teacher(actor); if(file.getUploaderId()!=actor) throw AuthorizationPolicy.invalid(); return files.saveAndFlush(file).getId();});
    }
    public FileView prepareFile(long actor,long fileId,PublishRequest publication) {
        return transaction(s->{
            UploadedFile file=policy.ownedFile(actor,fileId);
            if(publication!=null) {
                validatePublication(publication);
                if(publication.getQuizzes()!=null && !publication.getQuizzes().isEmpty())
                    quizzes.validateEdits(materials.findByUploadedFileId(fileId).map(Material::getId).orElse(null),publication.getQuizzes());
            }
            return fileView(file);
        });
    }
    public FileView prepareResource(long actor,String kind,long id) {
        return transaction(s->{
            UploadedFile file=kind.equals("PDF")?policy.ownedFile(actor,id):policy.owned(actor,id).getUploadedFile();
            return fileView(file);
        });
    }
    private FileView fileView(UploadedFile file) {
        boolean synthetic=file.getOriginalFileName().startsWith("indexing-synthetic")
            && file.getS3Key()!=null && file.getS3Key().matches("local/synthetic/indexing-pdf/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\\.pdf");
        return new FileView(file.getId(),file.getUploaderId(),file.getOriginalFileName(),file.getS3Key(),
            file.getJsonS3Key(),file.getS3Bucket(),file.getParsedAt(),synthetic);
    }
    private static void validatePublication(PublishRequest request) {
        if(request.getMaterialTitle()==null || request.getMaterialTitle().isBlank() || request.getMaterialTitle().length()>200
            || request.getEditedJson()==null) throw AuthorizationPolicy.invalid();
    }
    private UploadedFile lockFile(long actor,long id) {
        policy.teacher(actor);
        if(db.queryForList("SELECT id FROM uploaded_files WHERE id=? FOR UPDATE",Long.class,id).isEmpty()) throw AuthorizationPolicy.hidden();
        // Serialize with deletion/teacher edits before reloading the current relationship.
        db.queryForList("SELECT id FROM materials WHERE uploaded_file_id=? FOR UPDATE",Long.class,id);
        em.clear();
        return policy.ownedFile(actor,id);
    }
    public Publication publish(long actor,long fileId,PublishRequest request,String objectKey,String quizKey,IndexingSource.Snapshot source) {
        return transaction(s->{
            UploadedFile file=lockFile(actor,fileId);
            validatePublication(request);
            Material material=materials.findByUploadedFileIdAndDeletedAtIsNull(fileId).orElse(null);
            if(request.getQuizzes()!=null && !request.getQuizzes().isEmpty())
                quizzes.validateEdits(material==null?null:material.getId(),request.getQuizzes());
            if(material==null) material=Material.builder().uploadedFile(file).teacher(policy.actor(actor))
                .title(request.getMaterialTitle()).label(request.getLabelColor()).postStatus(PostStatus.PUBLISHED).build();
            else { material.setTitle(request.getMaterialTitle()); material.setLabel(request.getLabelColor()); material.setPostStatus(PostStatus.PUBLISHED); }
            file.setJsonS3Key(objectKey);
            file.setQuestionJsonS3Key(quizKey);
            materials.saveAndFlush(material);
            if(request.getQuizzes()!=null && !request.getQuizzes().isEmpty()) quizzes.saveQuizzes(material.getId(),actor,request.getQuizzes());
            em.flush();
            IndexingSummary summary=accept("MATERIAL",material.getId(),actor,source,IndexingSource.DEFAULT_SPEC);
            hooks.rollback(fileId,fileView(file).synthetic());
            return new Publication(material.getId(),file.getOriginalFileName(),objectKey,summary);
        });
    }
    public IndexingSummary completeInitial(long actor,long fileId,String jsonKey,IndexingSource.Snapshot source,String indexes) {
        return transaction(s->{
            UploadedFile file=lockFile(actor,fileId);
            file.setJsonS3Key(jsonKey); file.setParsedAt(LocalDateTime.now()); file.setIndexes(indexes); em.flush();
            IndexingSummary summary=accept("PDF",fileId,actor,source,IndexingSource.DEFAULT_SPEC);
            hooks.rollback(fileId,fileView(file).synthetic());
            return summary;
        });
    }
    public IndexingSummary request(long actor,String kind,long id,FileView prepared,IndexingSource.Snapshot source,String spec) {
        return transaction(s->{
            UploadedFile file=lockFile(actor,prepared.id());
            if(kind.equals("MATERIAL")) policy.owned(actor,id);
            if(!Objects.equals(file.getJsonS3Key(),prepared.jsonKey())) throw new IndexingFailure(409,"INDEXING_SOURCE_CHANGED");
            return accept(kind,id,actor,source,IndexingSource.spec(spec));
        });
    }
    private IndexingSummary accept(String kind,long objectId,long owner,IndexingSource.Snapshot source,String spec) {
        db.update("INSERT INTO index_resources(resource_kind,resource_id,owner_id,current_source_hash,created_at,updated_at) VALUES(?,?,?,'',UTC_TIMESTAMP(6),UTC_TIMESTAMP(6)) ON DUPLICATE KEY UPDATE id=id",kind,objectId,owner);
        Map<String,Object> resource=db.queryForMap("SELECT * FROM index_resources WHERE resource_kind=? AND resource_id=? FOR UPDATE",kind,objectId);
        if(number(resource,"owner_id")!=owner) throw AuthorizationPolicy.hidden();
        long pk=number(resource,"id"),revision=number(resource,"source_revision");
        if(!source.hash().equals(resource.get("current_source_hash"))) revision++;
        List<Map<String,Object>> existing=db.queryForList("SELECT * FROM index_jobs WHERE resource_pk=? AND source_revision=? AND index_spec=?",pk,revision,spec);
        if(!existing.isEmpty()) return summary(existing.get(0)); // Never promote an older request on replay.
        long seq=number(resource,"request_seq")+1;
        String id=UUID.randomUUID().toString();
        db.update("INSERT INTO index_jobs(job_id,resource_pk,source_revision,source_hash,snapshot_json,snapshot_bytes,index_spec,request_seq,state,next_delivery_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,'QUEUED',UTC_TIMESTAMP(6),UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))",
            id,pk,revision,source.hash(),source.json(),source.bytes(),spec,seq);
        Map<String,Object> job=db.queryForMap("SELECT * FROM index_jobs WHERE job_id=?",id);
        db.update("UPDATE index_jobs SET state='SUPERSEDED',completed_at=UTC_TIMESTAMP(6),updated_at=UTC_TIMESTAMP(6),failure_code='NEWER_REQUEST' WHERE resource_pk=? AND id<>? AND state IN ('QUEUED','PROCESSING')",pk,number(job,"id"));
        db.update("UPDATE index_resources SET source_revision=?,current_source_hash=?,request_seq=?,latest_job_id=?,updated_at=UTC_TIMESTAMP(6) WHERE id=?",revision,source.hash(),seq,number(job,"id"),pk);
        return summary(job);
    }
    public IndexingSummary resource(long actor,String kind,long id) {
        return transaction(s->{authorize(actor,kind,id); return resourceSummary(kind,id);});
    }
    public Map<Long,IndexingSummary> materialSummaries(long actor,List<Long> ids) {
        // This metadata-only read may join a caller's coherent transaction; it never
        // crosses an external boundary. In particular, do not hide its uncommitted rows.
        if(TransactionSynchronizationManager.isActualTransactionActive()) return readMaterialSummaries(actor,ids);
        return transaction(s->readMaterialSummaries(actor,ids));
    }
    private Map<Long,IndexingSummary> readMaterialSummaries(long actor,List<Long> ids) {
        policy.teacher(actor); Map<Long,IndexingSummary> result=new HashMap<>();
        for(long id:ids) { policy.owned(actor,id); result.put(id,resourceSummary("MATERIAL",id)); }
        return result;
    }
    private IndexingSummary resourceSummary(String kind,long id) {
        var rows=db.queryForList("SELECT j.* FROM index_resources r JOIN index_jobs j ON j.id=r.latest_job_id AND j.resource_pk=r.id WHERE r.resource_kind=? AND r.resource_id=?",kind,id);
        return rows.isEmpty()?IndexingSummary.none():summary(rows.get(0));
    }
    public IndexingSummary job(long actor,String id) { return transaction(s->summary(authorizedJob(actor,id,false))); }
    public IndexingSummary retry(long actor,String id,int expectedGeneration) {
        return transaction(s->{
            Map<String,Object> job=authorizedJob(actor,id,true);
            Map<String,Object> resource=db.queryForMap("SELECT * FROM index_resources WHERE id=?",number(job,"resource_pk"));
            int generation=(int)number(job,"execution_generation");
            if(expectedGeneration<0 || expectedGeneration>generation) throw new IndexingFailure(409,"INDEXING_GENERATION_CONFLICT");
            if(expectedGeneration<generation || !"FAILED".equals(job.get("state"))) return summary(job);
            if(number(resource,"latest_job_id")!=number(job,"id") || number(resource,"source_revision")!=number(job,"source_revision")
                || !resource.get("current_source_hash").equals(job.get("source_hash"))) throw new IndexingFailure(409,"INDEXING_SUPERSEDED");
            if(generation>=3 || number(job,"delivery_attempts")>=5) throw new IndexingFailure(409,"INDEXING_RETRY_LIMIT");
            db.update("UPDATE index_jobs SET state='QUEUED',delivery_state='PENDING',delivery_claim_token=NULL,delivery_deadline=NULL,next_delivery_at=UTC_TIMESTAMP(6),completed_at=NULL,failure_code=NULL,updated_at=UTC_TIMESTAMP(6) WHERE id=?",number(job,"id"));
            return summary(db.queryForMap("SELECT * FROM index_jobs WHERE id=?",number(job,"id")));
        });
    }
    private Map<String,Object> authorizedJob(long actor,String id,boolean lock) {
        policy.teacher(actor); IndexingSource.uuid(id);
        var rows=db.queryForList("SELECT * FROM index_jobs WHERE job_id=?",id);
        if(rows.isEmpty()) throw AuthorizationPolicy.hidden();
        Map<String,Object> job=rows.get(0);
        Map<String,Object> r=db.queryForMap("SELECT * FROM index_resources WHERE id=?",number(job,"resource_pk"));
        if(number(r,"owner_id")!=actor) throw AuthorizationPolicy.hidden();
        authorize(actor,(String)r.get("resource_kind"),number(r,"resource_id"));
        if(lock) {
            // Match publication/worker order: file -> material -> resource -> job.
            // The first permission check can become stale while these locks are acquired.
            String kind=(String)r.get("resource_kind");
            long objectId=number(r,"resource_id"),fileId=objectId;
            if(kind.equals("MATERIAL")) {
                var linked=db.queryForList("SELECT uploaded_file_id FROM materials WHERE id=?",Long.class,objectId);
                if(linked.isEmpty() || linked.get(0)==null) throw AuthorizationPolicy.hidden();
                fileId=linked.get(0);
            }
            lockFile(actor,fileId);
            r=db.queryForMap("SELECT * FROM index_resources WHERE id=? FOR UPDATE",number(job,"resource_pk"));
            job=db.queryForMap("SELECT * FROM index_jobs WHERE id=? FOR UPDATE",number(job,"id"));
            em.clear();
            if(number(r,"owner_id")!=actor) throw AuthorizationPolicy.hidden();
            if(kind.equals("MATERIAL")) {
                if(policy.owned(actor,objectId).getUploadedFile().getId()!=fileId) throw AuthorizationPolicy.hidden();
            } else policy.ownedFile(actor,objectId);
        }
        return job;
    }
    private void authorize(long actor,String kind,long id) { if(kind.equals("PDF")) policy.ownedFile(actor,id); else policy.owned(actor,id); }
    private IndexingSummary summary(Map<String,Object> job) {
        var resource=db.queryForMap("SELECT r.*,e.id active_id,e.job_pk active_job,j.source_revision active_revision,j.source_hash active_hash FROM index_resources r LEFT JOIN index_executions e ON e.id=r.active_execution_id AND e.state='ACTIVE' LEFT JOIN index_jobs j ON j.id=e.job_pk AND j.resource_pk=r.id AND j.state='SUCCEEDED' WHERE r.id=?",number(job,"resource_pk"));
        boolean readable=resource.get("active_revision")!=null && number(resource,"active_revision")==number(resource,"source_revision")
            && Objects.equals(resource.get("active_hash"),resource.get("current_source_hash"));
        boolean current=readable && number(resource,"active_job")==number(resource,"latest_job_id");
        boolean retry="FAILED".equals(job.get("state")) && number(job,"execution_generation")<3 && number(job,"delivery_attempts")<5
            && number(job,"id")==number(resource,"latest_job_id");
        return new IndexingSummary((String)job.get("job_id"),(String)job.get("state"),number(job,"source_revision"),readable,current,retry,(int)number(job,"execution_generation"));
    }
    private static long number(Map<String,Object> row,String key) { Object value=row.get(key); return value==null?0:((Number)value).longValue(); }
}
