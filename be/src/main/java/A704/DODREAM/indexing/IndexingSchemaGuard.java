package A704.DODREAM.indexing;

import org.springframework.boot.*;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component @Order(-90)
public class IndexingSchemaGuard implements ApplicationRunner {
    private final JdbcTemplate db;
    public IndexingSchemaGuard(JdbcTemplate db) { this.db=db; }
    public void run(ApplicationArguments args) {
        try {
            db.queryForList("SELECT id,resource_kind,resource_id,owner_id,source_revision,current_source_hash,request_seq,latest_job_id,active_execution_id,activation_count,created_at,updated_at FROM index_resources WHERE 1=0");
            db.queryForList("SELECT id,job_id,resource_pk,source_revision,source_hash,snapshot_json,snapshot_bytes,index_spec,request_seq,state,delivery_state,delivery_attempts,delivery_claim_token,delivery_deadline,next_delivery_at,last_delivered_at,execution_generation,created_at,updated_at,completed_at,failure_code FROM index_jobs WHERE 1=0");
            db.queryForList("SELECT id,job_pk,generation,candidate_name,claim_token,lease_until,state,expected_chunks,actual_chunks,content_digest,embedding_calls,started_at,completed_at,failure_code FROM index_executions WHERE 1=0");
            unique("index_resources","resource_kind,resource_id"); unique("index_jobs","job_id");
            unique("index_jobs","resource_pk,source_revision,index_spec");
            unique("index_executions","job_pk,generation"); unique("index_executions","candidate_name");
            Long keys=db.queryForObject("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND ((table_name='index_jobs' AND column_name IN ('job_id','source_hash','index_spec')) OR (table_name='index_executions' AND column_name IN ('candidate_name','claim_token'))) AND is_nullable='NO' AND collation_name='ascii_bin'",Long.class);
            if(keys==null || keys!=5) throw new IllegalStateException();
        } catch(RuntimeException failure) { throw new IllegalStateException("Apply V004__indexing_ledger.sql to the selected application database before startup"); }
    }
    private void unique(String table,String columns) {
        var values=db.queryForList("SELECT GROUP_CONCAT(column_name ORDER BY seq_in_index SEPARATOR ',') FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name=? AND non_unique=0 GROUP BY index_name",String.class,table);
        if(!values.contains(columns)) throw new IllegalStateException();
    }
}
