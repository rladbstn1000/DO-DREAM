package A704.DODREAM.quiz.grading;
import A704.DODREAM.authorization.AuthorizationPolicy;
import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.*;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.SimpleTransactionStatus;
import java.time.LocalDateTime;
import java.util.*;
import static A704.DODREAM.quiz.grading.GradingContract.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
class GradingAcceptanceRaceTests {
    @Test @SuppressWarnings("unchecked") void concurrentAcceptedKeyWinsBeforeInspectingNewLiveVersion() {
        var db=mock(JdbcTemplate.class);var policy=mock(AuthorizationPolicy.class);
        var tx=mock(PlatformTransactionManager.class);
        when(tx.getTransaction(any())).thenAnswer(invocation->new SimpleTransactionStatus());
        String key="00000000-0000-0000-0000-000000000001";
        var existing=new Attempt(7,"00000000-0000-0000-0000-000000000007",21,73,key,"fingerprint","PROCESSING",1,LocalDateTime.now(),null,LocalDateTime.now(),null);
        when(db.query(eq("SELECT * FROM grading_attempts WHERE student_id=? AND idempotency_key=?"),any(RowMapper.class),eq(21L),eq(key))).thenReturn(List.of());
        when(db.queryForObject(eq("SELECT * FROM grading_attempts WHERE student_id=? AND idempotency_key=?"),any(RowMapper.class),eq(21L),eq(key))).thenReturn(existing);
        when(db.update(startsWith("INSERT INTO grading_attempts("),anyString(),eq(21L),eq(73L),eq(key),eq("fingerprint"))).thenThrow(new DuplicateKeyException("concurrent key accepted"));
        var store=new GradingStore(db,policy,tx,mock(GradingLocalHooks.class),mock(EntityManager.class),mock(jakarta.persistence.EntityManagerFactory.class));
        var returned=store.accept(21,73,new Submission(key,"fingerprint",List.of(new Answer(9,0,"answer"))));
        assertSame(existing,returned);
        verify(db,never()).query(contains("FROM quizzes"),any(RowMapper.class),anyLong(),anyLong());
        var order=inOrder(tx,db);
        order.verify(tx).getTransaction(any());
        order.verify(db).query(anyString(),any(RowMapper.class),eq(21L),eq(key));
        order.verify(db).update(startsWith("INSERT INTO grading_attempts("),anyString(),eq(21L),eq(73L),eq(key),eq("fingerprint"));
        order.verify(tx).rollback(any());
        order.verify(tx).getTransaction(any());
        order.verify(db).queryForObject(anyString(),any(RowMapper.class),eq(21L),eq(key));
    }
}
