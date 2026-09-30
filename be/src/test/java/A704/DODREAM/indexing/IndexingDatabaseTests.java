package A704.DODREAM.indexing;

import A704.DODREAM.authorization.*;
import A704.DODREAM.file.entity.UploadedFile;
import A704.DODREAM.file.enums.PostStatus;
import A704.DODREAM.file.repository.UploadedFileRepository;
import A704.DODREAM.material.dto.PublishRequest;
import A704.DODREAM.material.entity.Material;
import A704.DODREAM.material.repository.MaterialRepository;
import A704.DODREAM.quiz.service.QuizService;
import A704.DODREAM.user.entity.*;
import jakarta.persistence.*;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.*;
import org.springframework.transaction.support.TransactionTemplate;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

/** Real MySQL/JPA; each case creates a new synthetic resource. Run while dispatcher is paused. */
@SpringBootTest @ActiveProfiles("local")
class IndexingDatabaseTests {
    @Autowired JdbcTemplate db;
    @Autowired EntityManager em;
    @Autowired EntityManagerFactory factory;
    @Autowired PlatformTransactionManager transactions;
    @Autowired IndexingStore store;
    @Autowired AuthorizationPolicy policy;
    @Autowired UploadedFileRepository files;
    @Autowired MaterialRepository materials;
    @Autowired QuizService quizzes;
    @Autowired IndexingLocalHooks hooks;
    long owner,file,material,outsider;
    String key;
    @BeforeEach void fixture() {
        key="local/synthetic/authz/"+UUID.randomUUID()+".json";
        new TransactionTemplate(transactions).executeWithoutResult(tx->{
            var teacher=User.create("INDEXING transactional owner",Role.TEACHER); em.persist(teacher);
            var other=User.create("INDEXING transactional outsider",Role.TEACHER); em.persist(other);
            var uploaded=UploadedFile.builder().originalFileName("indexing-synthetic-test.json").uploaderId(teacher.getId())
                .s3Key(key).jsonS3Key(key).s3Bucket("local-synthetic-fixtures").build(); em.persist(uploaded);
            var content=Material.builder().teacher(teacher).uploadedFile(uploaded).title("[INDEXING LOCAL] DB "+UUID.randomUUID()).postStatus(PostStatus.PUBLISHED).build(); em.persist(content);
            em.flush(); owner=teacher.getId(); outsider=other.getId(); file=uploaded.getId(); material=content.getId();
        });
    }
    IndexingSource.Snapshot snapshot(String text) { return IndexingSource.snapshot(List.of(text)); }
    IndexingSummary accept(String text,String spec) { return store.request(owner,"MATERIAL",material,store.prepareFile(owner,file,null),snapshot(text),spec); }
    long jobPk(IndexingSummary summary) { return db.queryForObject("SELECT id FROM index_jobs WHERE job_id=?",Long.class,summary.jobId()); }
    @Test void independentConcurrentRequestsShareOneDatabaseUniqueJob() throws Exception {
        var prepared=store.prepareFile(owner,file,null); var barrier=new CyclicBarrier(2);
        var executor=Executors.newFixedThreadPool(2);
        try {
            Callable<IndexingSummary> call=()->{barrier.await(5,TimeUnit.SECONDS); return store.request(owner,"MATERIAL",material,prepared,snapshot("same"),IndexingSource.DEFAULT_SPEC);};
            var a=executor.submit(call); var b=executor.submit(call);
            assertEquals(a.get(10,TimeUnit.SECONDS).jobId(),b.get(10,TimeUnit.SECONDS).jobId());
            assertEquals(1L,db.queryForObject("SELECT COUNT(*) FROM index_jobs j JOIN index_resources r ON r.id=j.resource_pk WHERE r.resource_kind='MATERIAL' AND r.resource_id=?",Long.class,material));
        } finally { executor.shutdownNow(); }
    }
    @Test void changedSourceAndNewSpecHaveDistinctMonotonicIdentityAndReplayDoesNotPromoteOldJob() {
        var a=accept("one",IndexingSource.DEFAULT_SPEC);
        var b=accept("one","local-hash8-content-v2");
        assertEquals(a.sourceRevision(),b.sourceRevision()); assertNotEquals(a.jobId(),b.jobId());
        assertEquals(a.jobId(),accept("one",IndexingSource.DEFAULT_SPEC).jobId());
        assertEquals(b.jobId(),store.resource(owner,"MATERIAL",material).jobId());
        var c=accept("two",IndexingSource.DEFAULT_SPEC);
        assertEquals(a.sourceRevision()+1,c.sourceRevision());
        assertEquals("SUPERSEDED",store.job(owner,b.jobId()).state());
    }
    @Test void publicationAndOutboxRollBackTogetherIncludingObjectReference() {
        var failure=mock(IndexingLocalHooks.class);
        doThrow(new IndexingFailure(503,"SYNTHETIC_ROLLBACK")).when(failure).rollback(eq(file),anyBoolean());
        var isolated=new IndexingStore(db,policy,em,factory,files,materials,quizzes,transactions,failure);
        String title=db.queryForObject("SELECT title FROM materials WHERE id=?",String.class,material);
        var request=PublishRequest.builder().materialTitle("changed").editedJson(Map.of("chapters",List.of(Map.of("type","content","content","one")))).build();
        assertThrows(IndexingFailure.class,()->isolated.publish(owner,file,request,"new-prepared-object",null,snapshot("one")));
        assertEquals(title,db.queryForObject("SELECT title FROM materials WHERE id=?",String.class,material));
        assertEquals(key,db.queryForObject("SELECT jsons3key FROM uploaded_files WHERE id=?",String.class,file));
        assertEquals(0L,db.queryForObject("SELECT COUNT(*) FROM index_resources WHERE resource_kind='MATERIAL' AND resource_id=?",Long.class,material));
    }
    @Test void sourceChangedDuringObjectReadCannotBeAcceptedUnderTheOldReference() {
        var prepared=store.prepareFile(owner,file,null);
        db.update("UPDATE uploaded_files SET jsons3key=? WHERE id=?",key+"-changed",file);
        assertEquals("INDEXING_SOURCE_CHANGED",assertThrows(IndexingFailure.class,()->store.request(owner,"MATERIAL",material,prepared,snapshot("old"),IndexingSource.DEFAULT_SPEC)).code());
        assertEquals(0L,db.queryForObject("SELECT COUNT(*) FROM index_resources WHERE resource_kind='MATERIAL' AND resource_id=?",Long.class,material));
    }
    @Test void previousActiveRemainsReadableOnSameSourceFailureButNotAfterContentChange() {
        var a=accept("one",IndexingSource.DEFAULT_SPEC); long id=jobPk(a);
        db.update("INSERT INTO index_executions(job_pk,generation,candidate_name,claim_token,lease_until,state,started_at) VALUES(?,1,?,?,DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 30 SECOND),'ACTIVE',UTC_TIMESTAMP(6))",id,"test-"+UUID.randomUUID(),UUID.randomUUID().toString());
        long execution=db.queryForObject("SELECT id FROM index_executions WHERE job_pk=?",Long.class,id);
        db.update("UPDATE index_jobs SET state='SUCCEEDED',execution_generation=1 WHERE id=?",id);
        db.update("UPDATE index_resources SET active_execution_id=?,activation_count=1 WHERE resource_kind='MATERIAL' AND resource_id=?",execution,material);
        assertTrue(store.resource(owner,"MATERIAL",material).activeCurrent());
        var b=accept("one","local-hash8-content-v2");
        db.update("UPDATE index_jobs SET state='FAILED',failure_code='SYNTHETIC_FAILURE' WHERE id=?",jobPk(b));
        var failed=store.resource(owner,"MATERIAL",material);
        assertTrue(failed.readable()); assertFalse(failed.activeCurrent());
        var c=accept("two",IndexingSource.DEFAULT_SPEC);
        assertFalse(c.readable());
        assertEquals(execution,db.queryForObject("SELECT active_execution_id FROM index_resources WHERE resource_kind='MATERIAL' AND resource_id=?",Long.class,material));
    }
    @Test void currentOwnerChecksApplyToStatusRetryAndDeletedResources() {
        var a=accept("one",IndexingSource.DEFAULT_SPEC);
        assertThrows(AuthorizationFailure.class,()->store.job(outsider,a.jobId()));
        assertThrows(AuthorizationFailure.class,()->store.retry(outsider,a.jobId(),0));
        db.update("UPDATE materials SET deleted_at=UTC_TIMESTAMP(6) WHERE id=?",material);
        assertThrows(AuthorizationFailure.class,()->store.job(owner,a.jobId()));
        assertThrows(AuthorizationFailure.class,()->store.resource(owner,"PDF",file));
    }
    @Test void manualRetryIsGenerationConditionedAndDeliveryBudgetNeverResets() {
        var a=accept("one",IndexingSource.DEFAULT_SPEC); long pk=jobPk(a);
        db.update("UPDATE index_jobs SET state='FAILED',execution_generation=1,delivery_attempts=2 WHERE id=?",pk);
        assertEquals("QUEUED",store.retry(owner,a.jobId(),1).state());
        assertEquals(2,db.queryForObject("SELECT delivery_attempts FROM index_jobs WHERE id=?",Integer.class,pk));
        db.update("UPDATE index_jobs SET state='FAILED',execution_generation=2 WHERE id=?",pk);
        assertEquals("FAILED",store.retry(owner,a.jobId(),1).state());
        db.update("UPDATE index_jobs SET delivery_attempts=5 WHERE id=?",pk);
        assertEquals("INDEXING_RETRY_LIMIT",assertThrows(IndexingFailure.class,()->store.retry(owner,a.jobId(),2)).code());
    }
    @Test void retryRechecksMaterialDeletionCommittedAfterItsInitialAuthorization() throws Exception {
        retryRechecksAfterConcurrentChange("MATERIAL",()->db.update("UPDATE materials SET deleted_at=UTC_TIMESTAMP(6) WHERE id=?",material));
    }
    @Test void retryRechecksPdfOwnerCommittedAfterItsInitialAuthorization() throws Exception {
        retryRechecksAfterConcurrentChange("PDF",()->db.update("UPDATE uploaded_files SET uploader_id=? WHERE id=?",outsider,file));
    }
    private void retryRechecksAfterConcurrentChange(String kind,Runnable change) throws Exception {
        long objectId=kind.equals("PDF")?file:material;
        var accepted=store.request(owner,kind,objectId,store.prepareFile(owner,file,null),snapshot("immutable"),IndexingSource.DEFAULT_SPEC);
        long pk=jobPk(accepted);
        db.update("UPDATE index_jobs SET state='FAILED',execution_generation=1,delivery_attempts=2 WHERE id=?",pk);
        var before=db.queryForMap("SELECT state,execution_generation,delivery_attempts,snapshot_json,source_hash FROM index_jobs WHERE id=?",pk);
        var checked=new CountDownLatch(1); var changed=new CountDownLatch(1);
        // Only pause after the real policy has read the real database. The concurrent
        // connection commits while the retry transaction still holds its old JPA view.
        var observed=mock(AuthorizationPolicy.class,org.mockito.AdditionalAnswers.delegatesTo(policy));
        if(kind.equals("PDF")) doAnswer(invocation->{
            var result=policy.ownedFile(owner,file); checked.countDown();
            assertTrue(changed.await(5,TimeUnit.SECONDS)); return result;
        }).when(observed).ownedFile(owner,file);
        else doAnswer(invocation->{
            var result=policy.owned(owner,material); checked.countDown();
            assertTrue(changed.await(5,TimeUnit.SECONDS)); return result;
        }).when(observed).owned(owner,material);
        var isolated=new IndexingStore(db,observed,em,factory,files,materials,quizzes,transactions,hooks);
        var executor=Executors.newSingleThreadExecutor();
        try {
            var pending=executor.submit(()->isolated.retry(owner,accepted.jobId(),1));
            assertTrue(checked.await(5,TimeUnit.SECONDS));
            change.run(); changed.countDown();
            var failure=assertThrows(ExecutionException.class,()->pending.get(10,TimeUnit.SECONDS));
            assertEquals(org.springframework.http.HttpStatus.NOT_FOUND,assertInstanceOf(AuthorizationFailure.class,failure.getCause()).getStatus());
            assertEquals(before,db.queryForMap("SELECT state,execution_generation,delivery_attempts,snapshot_json,source_hash FROM index_jobs WHERE id=?",pk));
            assertEquals(0L,db.queryForObject("SELECT COUNT(*) FROM index_executions WHERE job_pk=?",Long.class,pk));
            assertEquals(0L,db.queryForObject("SELECT activation_count FROM index_resources WHERE resource_kind=? AND resource_id=?",Long.class,kind,objectId));
        } finally { changed.countDown(); executor.shutdownNow(); }
    }
    @Test void initialAndPublishedResourcesDoNotShareLogicalJobsAndShortTransactionsReleaseConnections() {
        var a=accept("same",IndexingSource.DEFAULT_SPEC);
        var b=store.request(owner,"PDF",file,store.prepareFile(owner,file,null),snapshot("same"),IndexingSource.DEFAULT_SPEC);
        assertNotEquals(a.jobId(),b.jobId());
        var view=factory.createEntityManager();
        org.springframework.transaction.support.TransactionSynchronizationManager.bindResource(factory,new org.springframework.orm.jpa.EntityManagerHolder(view));
        try {
            store.prepareFile(owner,file,null);
            assertDoesNotThrow(()->hooks.boundary(file,false));
            assertFalse(view.unwrap(org.hibernate.engine.spi.SessionImplementor.class).getJdbcCoordinator().getLogicalConnection().isPhysicallyConnected());
        } finally {
            org.springframework.transaction.support.TransactionSynchronizationManager.unbindResource(factory); view.close();
        }
    }
}
