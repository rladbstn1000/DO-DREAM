package A704.DODREAM.quiz.grading;
import org.springframework.boot.*;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
@Component @Order(-100)
public class GradingSchemaGuard implements ApplicationRunner {
    private final JdbcTemplate db;
    public GradingSchemaGuard(JdbcTemplate db) { this.db=db; }
    public void run(ApplicationArguments args) {
        try {
            db.queryForList("SELECT id,attempt_id,student_id,material_id,idempotency_key,request_fingerprint,state,execution_generation,execution_token_hash,deadline_at,dispatched_at,created_at,completed_at,failure_code FROM grading_attempts WHERE 1=0");
            db.queryForList("SELECT attempt_id,quiz_id,quiz_version,question_number,question_type,title,question_content,correct_answer,student_answer,grading_version FROM grading_attempt_items WHERE 1=0");
            db.queryForList("SELECT attempt_id,quiz_id,is_correct,ai_feedback FROM grading_attempt_results WHERE 1=0");
            requireUnique("grading_attempts","student_id,idempotency_key");
            requireUnique("grading_attempts","attempt_id");
            requireUnique("grading_attempt_items","attempt_id,quiz_id");
            requireUnique("grading_attempt_results","attempt_id,quiz_id");
            requireUnique("student_quiz_logs","attempt_id,quiz_id");
            Long keys=db.queryForObject("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='grading_attempts' AND column_name IN ('idempotency_key','request_fingerprint','attempt_id') AND is_nullable='NO' AND collation_name='ascii_bin'",Long.class);
            if(keys==null || keys!=3) throw new IllegalStateException();
        } catch(RuntimeException failure) { throw new IllegalStateException("Apply V003__grading_attempts.sql to the selected application database before startup"); }
    }
    private void requireUnique(String table,String columns) {
        var indexes=db.queryForList("SELECT GROUP_CONCAT(column_name ORDER BY seq_in_index SEPARATOR ',') FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name=? AND non_unique=0 GROUP BY index_name",String.class,table);
        if(!indexes.contains(columns)) throw new IllegalStateException();
    }
}
