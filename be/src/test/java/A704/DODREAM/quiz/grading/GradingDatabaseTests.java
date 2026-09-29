package A704.DODREAM.quiz.grading;

import A704.DODREAM.authorization.AuthorizationPolicy;
import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;
import java.util.*;
import static A704.DODREAM.quiz.grading.GradingContract.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

/** Actual MySQL transactions; only new attempts on dedicated synthetic grading fixtures. */
@SpringBootTest @ActiveProfiles("local")
class GradingDatabaseTests {
    @Autowired JdbcTemplate db;
    @Autowired GradingStore store;
    @Autowired AuthorizationPolicy policy;
    @Autowired PlatformTransactionManager transactions;
    @Autowired EntityManager em;
    @Autowired javax.sql.DataSource source;
    @Autowired GradingLocalHooks hooks;
    @Autowired jakarta.persistence.EntityManagerFactory factory;
    long student,material;
    List<Map<String,Object>> quizRows;
    @BeforeEach void fixtures() {
        material=db.queryForObject("SELECT id FROM materials WHERE title='[GRADING LOCAL] phase3a'",Long.class);
        student=db.queryForObject("SELECT student_id FROM material_shares WHERE material_id=? ORDER BY student_id LIMIT 1",Long.class,material);
        quizRows=db.queryForList("SELECT id,version FROM quizzes WHERE material_id=? ORDER BY id",material);
    }
    Submission input(String key,String answer) {
        var list=JSON.createArrayNode();
        for(var q:quizRows) list.addObject().put("quizId",((Number)q.get("id")).longValue()).put("version",((Number)q.get("version")).longValue()).put("answer",answer);
        return parse(key,material,JSON.createObjectNode().set("answers",list));
    }
    Attempt accepted() { return store.accept(student,material,input(UUID.randomUUID().toString(),"synthetic")); }
    List<Result> result(Execution e) { return e.items().stream().map(i->new Result(i.quizId(),true,"synthetic feedback")).toList(); }
    long logs(Attempt a) { return db.queryForObject("SELECT COUNT(*) FROM student_quiz_logs WHERE attempt_id=?",Long.class,a.id()); }
    @Test void localObservationReleasesConnectionBeforeProviderEvenInEmptySynchronizationScope() {
        var a=accepted();
        var outer=new org.springframework.transaction.support.TransactionTemplate(transactions);
        outer.setPropagationBehavior(org.springframework.transaction.TransactionDefinition.PROPAGATION_NOT_SUPPORTED);
        // Reproduce why a bare JdbcTemplate query was unsafe in the old orchestration.
        outer.executeWithoutResult(status -> {
            assertTrue(org.springframework.transaction.support.TransactionSynchronizationManager.isSynchronizationActive());
            assertFalse(org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive());
            assertTrue(hooks.enabled(a));
            assertTrue(org.springframework.transaction.support.TransactionSynchronizationManager.hasResource(source));
        });
        // The production path closes its own short transaction before reaching the provider.
        var view=factory.createEntityManager();
        org.springframework.transaction.support.TransactionSynchronizationManager.bindResource(factory,new org.springframework.orm.jpa.EntityManagerHolder(view));
        try {
            outer.executeWithoutResult(status -> {
                store.authorize(student,material);
                assertTrue(store.localFixture(a));
                assertFalse(org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive());
                assertFalse(org.springframework.transaction.support.TransactionSynchronizationManager.hasResource(source));
                assertFalse(view.unwrap(org.hibernate.engine.spi.SessionImplementor.class).getJdbcCoordinator().getLogicalConnection().isPhysicallyConnected());
                assertDoesNotThrow(() -> hooks.boundary(a,false));
            });
        } finally {
            org.springframework.transaction.support.TransactionSynchronizationManager.unbindResource(factory);
            view.close();
        }
    }
    @Test void databaseUniqueReplaysSameLogicalSubmission() {
        var body=input(UUID.randomUUID().toString(),"exact ");
        var a=store.accept(student,material,body); var b=store.accept(student,material,body);
        assertEquals(a.id(),b.id());
        assertEquals(1L,db.queryForObject("SELECT COUNT(*) FROM grading_attempts WHERE student_id=? AND idempotency_key=?",Long.class,student,body.key()));
        assertEquals(quizRows.size(),db.queryForObject("SELECT COUNT(*) FROM grading_attempt_items WHERE attempt_id=?",Integer.class,a.id()));
        assertEquals("IDEMPOTENCY_KEY_CONFLICT",assertThrows(GradingFailure.class,()->store.accept(student,material,input(body.key(),"different"))).code);
    }
    @Test void sameKeyAcrossStudentsDoesNotCollideOrAuthorizeOtherAttempt() {
        long other=db.queryForObject("SELECT student_id FROM material_shares WHERE material_id=? AND student_id<>? LIMIT 1",Long.class,material,student);
        var body=input(UUID.randomUUID().toString(),"same");
        var a=store.accept(student,material,body); var b=store.accept(other,material,body);
        assertNotEquals(a.id(),b.id());
        assertThrows(A704.DODREAM.authorization.AuthorizationFailure.class,()->store.view(other,material,a.attemptId()));
    }
    @Test void atomicCompletionAndReplayDoNotCreateExtraLogs() {
        var a=accepted(); var e=store.claim(student,material,a.attemptId(),null,true);
        assertTrue(store.dispatch(e)); store.complete(e,result(e)); store.complete(e,result(e));
        assertEquals("SUCCEEDED",store.view(student,material,a.attemptId()).attempt().state());
        assertEquals(quizRows.size(),logs(a));
        assertTrue(store.view(student,material,a.attemptId()).results().stream().allMatch(r->Boolean.TRUE.equals(r.getSnapshotAvailable()) && r.getVersion()!=null && r.getCorrectAnswer()!=null));
        assertNull(store.claim(student,material,a.attemptId(),null,true));
    }
    @Test void partialFinalizationRollsBackBothResultsAndLogs() {
        var fault=mock(GradingLocalHooks.class);
        var isolated=new GradingStore(db,policy,transactions,fault,em,em.getEntityManagerFactory());
        var a=accepted(); var e=store.claim(student,material,a.attemptId(),null,true); store.dispatch(e);
        doThrow(new IllegalStateException("synthetic partial write")).when(fault).failAfterFirstLog(any());
        assertThrows(IllegalStateException.class,()->isolated.complete(e,result(e)));
        assertEquals(0,logs(a));
        assertEquals(0L,db.queryForObject("SELECT COUNT(*) FROM grading_attempt_results WHERE attempt_id=?",Long.class,a.id()));
        store.fail(e,"UNKNOWN","TEST_FINALIZATION_FAILURE");
        assertEquals("UNKNOWN",store.view(student,material,a.attemptId()).attempt().state());
    }
    @Test void deadlineRecoveryFencesOldWorkerAndFreezesRetryGeneration() {
        var a=accepted();var old=store.claim(student,material,a.attemptId(),null,true);store.dispatch(old);
        db.update("UPDATE grading_attempts SET deadline_at=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 SECOND) WHERE id=?",a.id());
        assertEquals("UNKNOWN",store.view(student,material,a.attemptId()).attempt().state());
        assertEquals("UNKNOWN_CONFIRMATION_REQUIRED",assertThrows(GradingFailure.class,()->store.claim(student,material,a.attemptId(),new Retry(1,false),false)).code);
        var newer=store.claim(student,material,a.attemptId(),new Retry(1,true),false);
        assertEquals(2,newer.attempt().generation());
        assertNull(store.claim(student,material,a.attemptId(),new Retry(1,true),false));
        store.complete(old,result(old));assertEquals(0,logs(a));
        store.dispatch(newer);store.complete(newer,result(newer));assertEquals(quizRows.size(),logs(a));
    }
    @Test void authorizationDenialRollsBackThenPersistsRevokedWithoutPartialGrades() {
        var a=accepted();var e=store.claim(student,material,a.attemptId(),null,true);assertTrue(store.dispatch(e));
        db.update("UPDATE materials SET deleted_at=UTC_TIMESTAMP(6) WHERE id=?",material);
        try {
            assertDoesNotThrow(()->store.complete(e,result(e)));
            assertEquals("REVOKED",db.queryForObject("SELECT state FROM grading_attempts WHERE id=?",String.class,a.id()));
            assertEquals(0,logs(a));
            assertEquals(0L,db.queryForObject("SELECT COUNT(*) FROM grading_attempt_results WHERE attempt_id=?",Long.class,a.id()));
        } finally { db.update("UPDATE materials SET deleted_at=NULL WHERE id=?",material); }
    }
    @Test void undispatchedExpirationAndRetryLimitArePersisted() {
        var a=accepted();var e=store.claim(student,material,a.attemptId(),null,true);
        db.update("UPDATE grading_attempts SET deadline_at=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 SECOND) WHERE id=?",a.id());
        assertEquals("FAILED",store.view(student,material,a.attemptId()).attempt().state());
        assertFalse(store.dispatch(e));
        for(int n=1;n<3;n++) { var next=store.claim(student,material,a.attemptId(),new Retry(n,false),false); store.fail(next,"FAILED","SYNTHETIC_KNOWN_FAILURE"); }
        assertEquals("RETRY_LIMIT_REACHED",assertThrows(GradingFailure.class,()->store.claim(student,material,a.attemptId(),new Retry(3,true),false)).code);
        assertEquals(0,logs(a));
    }
}
