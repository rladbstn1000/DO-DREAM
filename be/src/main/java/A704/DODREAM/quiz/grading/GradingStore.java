package A704.DODREAM.quiz.grading;

import A704.DODREAM.authorization.*;
import A704.DODREAM.quiz.dto.GradingResultDto;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDateTime;
import java.security.SecureRandom;
import java.util.*;
import static A704.DODREAM.quiz.grading.GradingContract.*;

/** All methods own short transactions. No provider calls or waits are permitted here. */
@Service
public class GradingStore {
    private final JdbcTemplate db;
    private final jakarta.persistence.EntityManager em;
    private final jakarta.persistence.EntityManagerFactory factory;
    private final AuthorizationPolicy policy;
    private final TransactionTemplate tx;
    private final GradingLocalHooks hooks;
    private static final SecureRandom RANDOM = new SecureRandom();

    public GradingStore(
            JdbcTemplate db,
            AuthorizationPolicy policy,
            PlatformTransactionManager manager,
            GradingLocalHooks hooks,
            jakarta.persistence.EntityManager em,
            jakarta.persistence.EntityManagerFactory factory) {
        this.db = db;
        this.policy = policy;
        this.hooks = hooks;
        this.em = em;
        this.factory = factory;
        tx = new TransactionTemplate(manager);
        tx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
        tx.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
        tx.setTimeout(8);
    }

    private <T> T transaction(org.springframework.transaction.support.TransactionCallback<T> work) {
        // OSIV owns a request-scoped EntityManager whose default connection handling holds
        // connections until the request ends. Grading transactions must own and close theirs.
        Object viewHolder = null;
        if (!org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive())
            viewHolder = org.springframework.transaction.support.TransactionSynchronizationManager
                    .unbindResourceIfPossible(factory);
        try {
            return tx.execute(work);
        } finally {
            if (viewHolder != null)
                org.springframework.transaction.support.TransactionSynchronizationManager.bindResource(factory, viewHolder);
        }
    }

    private void transactionVoid(java.util.function.Consumer<org.springframework.transaction.TransactionStatus> work) {
        transaction(status -> {
            work.accept(status);
            return null;
        });
    }

    private void currentPermission(long student, long material) {
        // OSIV may retain entities loaded during acceptance. Never reuse them at finalization.
        em.clear();
        policy.studentMaterial(student, material);
    }

    public void authorize(long student, long material) {
        transactionVoid(s -> currentPermission(student, material));
    }

    public boolean localFixture(Attempt attempt) {
        return Boolean.TRUE.equals(transaction(s -> hooks.enabled(attempt)));
    }

    public Attempt accept(long student, long material, Submission input) {
        try {
            return transaction(s -> {
                currentPermission(student, material);
                List<Attempt> found = db.query(
                        "SELECT * FROM grading_attempts WHERE student_id=? AND idempotency_key=?",
                        this::attempt, student, input.key());
                if (!found.isEmpty()) return replay(found.get(0), material, input.fingerprint());
                // Claim the UNIQUE key first. A simultaneous replay waits here and must not
                // fail a newer live quiz version before discovering the accepted submission.
                String publicId = UUID.randomUUID().toString();
                db.update(
                        "INSERT INTO grading_attempts(attempt_id,student_id,material_id,idempotency_key,request_fingerprint,state,execution_generation,created_at,deadline_at) VALUES(?,?,?,?,?,'READY',0,UTC_TIMESTAMP(6),DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 30 SECOND))",
                        publicId, student, material, input.key(), input.fingerprint());
                Attempt acceptedRow = load(publicId, false);
                // Deterministic lock order gives a coherent snapshot and serializes concurrent teacher edits.
                List<Item> snapshots = new ArrayList<>();
                for (Answer a : input.answers()) {
                    List<Item> matches = db.query(
                            "SELECT id,version,question_number,question_type,title,content,correct_answer FROM quizzes WHERE id=? AND material_id=? FOR UPDATE",
                            (r, n) -> new Item(
                                    r.getLong("id"),
                                    r.getLong("version"),
                                    r.getInt("question_number"),
                                    r.getString("question_type"),
                                    r.getString("title"),
                                    r.getString("content"),
                                    r.getString("correct_answer"),
                                    a.answer(),
                                    "snapshot-v1"),
                            a.quizId(), material);
                    if (matches.isEmpty()) throw AuthorizationPolicy.invalid();
                    Item item = matches.get(0);
                    if (item.version() != a.version()) throw error(409, "QUIZ_VERSION_CONFLICT");
                    if (item.content() == null
                            || item.content().codePointCount(0, item.content().length()) > 20000
                            || item.correctAnswer() == null
                            || item.correctAnswer().codePointCount(0, item.correctAnswer().length()) > 2000)
                        throw error(409, "QUIZ_CONTENT_UNSUPPORTED");
                    snapshots.add(item);
                }
                for (Item i : snapshots)
                    db.update(
                            "INSERT INTO grading_attempt_items(attempt_id,quiz_id,quiz_version,question_number,question_type,title,question_content,correct_answer,student_answer,grading_version) VALUES(?,?,?,?,?,?,?,?,?,?)",
                            acceptedRow.id(), i.quizId(), i.version(), i.number(), i.type(), i.title(),
                            i.content(), i.correctAnswer(), i.answer(), i.gradingVersion());
                return acceptedRow;
            });
        } catch (DuplicateKeyException race) {
            return transaction(s -> {
                currentPermission(student, material);
                return replay(
                        db.queryForObject(
                                "SELECT * FROM grading_attempts WHERE student_id=? AND idempotency_key=?",
                                this::attempt, student, input.key()),
                        material, input.fingerprint());
            });
        }
    }

    private Attempt replay(Attempt a, long material, String fingerprint) {
        if (a.materialId() != material || !a.fingerprint().equals(fingerprint))
            throw error(409, "IDEMPOTENCY_KEY_CONFLICT");
        return a;
    }

    public View view(long student, long material, String id) {
        uuid(id);
        return transaction(s -> {
            Attempt a = authorized(student, material, id);
            expire(a);
            return view(load(id, false));
        });
    }

    public Execution claim(long student, long material, String id, Retry retry, boolean initial) {
        return transaction(s -> {
            Attempt a = authorized(student, material, id);
            expire(a);
            a = load(id, false);
            if (initial) {
                if (!a.state().equals("READY") || a.generation() != 0) return null;
            } else {
                if (retry.expectedGeneration() < a.generation()) return null;
                if (retry.expectedGeneration() > a.generation()) throw error(409, "RECOVERY_GENERATION_CONFLICT");
                if (a.state().equals("SUCCEEDED") || a.state().equals("PROCESSING") || a.state().equals("REVOKED"))
                    return null;
                if (a.generation() >= 3) throw error(409, "RETRY_LIMIT_REACHED");
                if (a.state().equals("UNKNOWN") && !retry.confirmUnknown())
                    throw error(409, "UNKNOWN_CONFIRMATION_REQUIRED");
            }
            byte[] secret = new byte[32];
            RANDOM.nextBytes(secret);
            String capability = Base64.getUrlEncoder().withoutPadding().encodeToString(secret);
            db.update(
                    "UPDATE grading_attempts SET state='PROCESSING',execution_generation=execution_generation+1,execution_token_hash=?,deadline_at=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 30 SECOND),dispatched_at=NULL,failure_code=NULL WHERE id=?",
                    hash(capability), a.id());
            return new Execution(load(id, false), capability, items(a.id()));
        });
    }

    public boolean dispatch(Execution e) {
        try {
            return Boolean.TRUE.equals(transaction(s -> {
                Attempt a = load(e.attempt().attemptId(), true);
                if (!current(a, e)) return false;
                currentPermission(a.studentId(), a.materialId());
                if (expire(a)) return false;
                db.update("UPDATE grading_attempts SET dispatched_at=UTC_TIMESTAMP(6) WHERE id=?", a.id());
                return true;
            }));
        } catch (AuthorizationFailure denied) {
            // AuthorizationPolicy participates in this transaction. Its denial rolls it back;
            // record the terminal state only after that failed transaction has finished.
            revokeExecution(e);
            return false;
        }
    }

    public void fail(Execution e, String state, String code) {
        transactionVoid(s -> {
            Attempt a = load(e.attempt().attemptId(), true);
            if (current(a, e))
                db.update(
                        "UPDATE grading_attempts SET state=?,failure_code=?,completed_at=UTC_TIMESTAMP(6),execution_token_hash=NULL WHERE id=?",
                        state, code, a.id());
        });
    }

    public void complete(Execution e, List<Result> results) {
        try {
            transactionVoid(s -> {
                Attempt a = load(e.attempt().attemptId(), true);
                if (!current(a, e) || expire(a)) return;
                currentPermission(a.studentId(), a.materialId());
                Map<Long, Item> snapshot = new HashMap<>();
                items(a.id()).forEach(i -> snapshot.put(i.quizId(), i));
                int written = 0;
                for (Result r : results) {
                    Item i = snapshot.remove(r.quizId());
                    if (i == null) throw error(502, "INVALID_PROVIDER_RESPONSE");
                    db.update(
                            "INSERT INTO grading_attempt_results(attempt_id,quiz_id,is_correct,ai_feedback) VALUES(?,?,?,?)",
                            a.id(), r.quizId(), r.correct(), r.feedback());
                    db.update(
                            "INSERT INTO student_quiz_logs(quiz_id,student_id,student_answer,is_correct,ai_feedback,solved_at,attempt_id,submitted_at,snapshot_correct_answer,snapshot_question_content,snapshot_quiz_version,grading_version) VALUES(?,?,?,?,?,UTC_TIMESTAMP(6),?,?,?,?,?,?)",
                            i.quizId(), a.studentId(), i.answer(), r.correct(), r.feedback(), a.id(),
                            a.created(), i.correctAnswer(), i.content(), i.version(), i.gradingVersion());
                    if (++written == 1) hooks.failAfterFirstLog(a);
                }
                if (!snapshot.isEmpty()) throw error(502, "INVALID_PROVIDER_RESPONSE");
                db.update(
                        "UPDATE grading_attempts SET state='SUCCEEDED',completed_at=UTC_TIMESTAMP(6),execution_token_hash=NULL,failure_code=NULL WHERE id=?",
                        a.id());
            });
        } catch (AuthorizationFailure denied) {
            revokeExecution(e);
        }
    }

    private void revokeExecution(Execution e) {
        transactionVoid(status -> {
            Attempt a = load(e.attempt().attemptId(), true);
            if (current(a, e)) revoke(a);
        });
    }

    private boolean current(Attempt a, Execution e) {
        return a.state().equals("PROCESSING") && a.generation() == e.attempt().generation();
    }

    private void revoke(Attempt a) {
        db.update(
                "UPDATE grading_attempts SET state='REVOKED',failure_code='ACCESS_REVOKED',execution_token_hash=NULL,completed_at=UTC_TIMESTAMP(6) WHERE id=?",
                a.id());
    }

    private boolean expire(Attempt a) {
        if (!(a.state().equals("READY") || a.state().equals("PROCESSING"))) return false;
        int changed = db.update(
                "UPDATE grading_attempts SET state=IF(dispatched_at IS NULL,'FAILED','UNKNOWN'),failure_code=IF(dispatched_at IS NULL,'BEFORE_DISPATCH_EXPIRED','EXECUTION_DEADLINE_EXPIRED'),execution_token_hash=NULL,completed_at=UTC_TIMESTAMP(6) WHERE id=? AND deadline_at<=UTC_TIMESTAMP(6) AND state IN ('READY','PROCESSING')",
                a.id());
        return changed > 0;
    }

    private Attempt authorized(long student, long material, String id) {
        currentPermission(student, material);
        Attempt a = load(id, true);
        if (a.studentId() != student || a.materialId() != material) throw AuthorizationPolicy.hidden();
        return a;
    }

    private Attempt load(String id, boolean lock) {
        List<Attempt> found = db.query(
                "SELECT * FROM grading_attempts WHERE attempt_id=?" + (lock ? " FOR UPDATE" : ""),
                this::attempt, id);
        if (found.isEmpty()) throw AuthorizationPolicy.hidden();
        return found.get(0);
    }

    private List<Item> items(long id) {
        return db.query(
                "SELECT * FROM grading_attempt_items WHERE attempt_id=? ORDER BY quiz_id",
                (r, n) -> new Item(
                        r.getLong("quiz_id"),
                        r.getLong("quiz_version"),
                        r.getInt("question_number"),
                        r.getString("question_type"),
                        r.getString("title"),
                        r.getString("question_content"),
                        r.getString("correct_answer"),
                        r.getString("student_answer"),
                        r.getString("grading_version")),
                id);
    }

    private View view(Attempt a) {
        List<GradingResultDto> results = a.state().equals("SUCCEEDED")
                ? db.query(
                        "SELECT i.*,r.is_correct,r.ai_feedback FROM grading_attempt_items i JOIN grading_attempt_results r ON r.attempt_id=i.attempt_id AND r.quiz_id=i.quiz_id WHERE i.attempt_id=? ORDER BY i.quiz_id",
                        (r, n) -> GradingResultDto.builder()
                                .attemptId(a.attemptId())
                                .quizId(r.getLong("quiz_id"))
                                .version(r.getLong("quiz_version"))
                                .snapshotAvailable(true)
                                .questionContent(r.getString("question_content"))
                                .gradingVersion(r.getString("grading_version"))
                                .correctAnswer(r.getString("correct_answer"))
                                .studentAnswer(r.getString("student_answer"))
                                .isCorrect(r.getBoolean("is_correct"))
                                .aiFeedback(r.getString("ai_feedback"))
                                .build(),
                        a.id())
                : List.of();
        return new View(a, results);
    }

    private Attempt attempt(ResultSet r, int n) throws SQLException {
        return new Attempt(
                r.getLong("id"),
                r.getString("attempt_id"),
                r.getLong("student_id"),
                r.getLong("material_id"),
                r.getString("idempotency_key"),
                r.getString("request_fingerprint"),
                r.getString("state"),
                r.getInt("execution_generation"),
                r.getObject("deadline_at", LocalDateTime.class),
                r.getObject("dispatched_at", LocalDateTime.class),
                r.getObject("created_at", LocalDateTime.class),
                r.getString("failure_code"));
    }
}
