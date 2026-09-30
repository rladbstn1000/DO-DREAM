package A704.DODREAM.quiz.grading;

import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import javax.sql.DataSource;
import java.nio.file.*;
import java.time.Instant;
import java.util.Map;
import static A704.DODREAM.quiz.grading.GradingContract.*;

/** Only synthetic local fixtures can use filesystem fault controls; never request headers. */
@Component
public class GradingLocalHooks {
    private final boolean local;
    private final JdbcTemplate db;
    private final DataSource source;
    private final jakarta.persistence.EntityManagerFactory factory;
    private final Path directory;
    public GradingLocalHooks(Environment environment,JdbcTemplate db,DataSource source,jakarta.persistence.EntityManagerFactory factory) {
        local=environment.acceptsProfiles(Profiles.of("local")); this.db=db; this.source=source; this.factory=factory;
        directory=Path.of(environment.getProperty("LOCAL_DATA_DIR","/app/local-data"),"grading-controls");
    }
    public boolean enabled(Attempt a) {
        if(!local) return false;
        return Boolean.TRUE.equals(db.queryForObject("SELECT title LIKE '[GRADING LOCAL]%' FROM materials WHERE id=?",Boolean.class,a.materialId()));
    }
    private Path control(Attempt a) { return directory.resolve(a.key()+"."+a.generation()+".json"); }
    private boolean mode(Attempt a,String value) {
        try { var p=control(a); return !Files.isSymbolicLink(p) && Files.size(p)<4096 && value.equals(JSON.readTree(Files.readString(p)).path("mode").asText()); }
        catch(Exception ignored) { return false; }
    }
    public void gate(Attempt a,String point,boolean enabled) {
        if(!enabled || !mode(a,point)) return;
        event(a,point);
        Path release=directory.resolve(a.key()+"."+a.generation()+".release");
        long end=System.nanoTime()+45_000_000_000L;
        try { while(System.nanoTime()<end && !Files.exists(release)) Thread.sleep(100); }
        catch(InterruptedException e) { Thread.currentThread().interrupt(); throw error(503,"LOCAL_EXECUTION_INTERRUPTED"); }
    }
    public void boundary(Attempt a,boolean enabled) {
        boolean active=TransactionSynchronizationManager.isActualTransactionActive();
        boolean bound=TransactionSynchronizationManager.hasResource(source);
        Object resource=TransactionSynchronizationManager.getResource(factory);
        boolean physical=resource instanceof org.springframework.orm.jpa.EntityManagerHolder holder
            && holder.getEntityManager().isOpen()
            && holder.getEntityManager().unwrap(org.hibernate.engine.spi.SessionImplementor.class)
                .getJdbcCoordinator().getLogicalConnection().isPhysicallyConnected();
        if(enabled) writeEvent(a,"provider_boundary",Map.of("transactionActive",active,"connectionBound",bound,"hibernateConnectionHeld",physical));
        if(active || bound || physical) throw error(503,"GRADING_TRANSACTION_BOUNDARY");
    }
    public void failAfterFirstLog(Attempt a) { if(enabled(a) && mode(a,"fail_after_first_log")) throw error(503,"LOCAL_FINALIZATION_FAILURE"); }
    public void afterCommit(Attempt a,boolean enabled) { gate(a,"after_commit",enabled); if(enabled && mode(a,"after_commit_response_lost")) throw error(503,"LOCAL_RESPONSE_LOST"); }
    private void event(Attempt a,String name) { writeEvent(a,name,Map.of()); }
    private void writeEvent(Attempt a,String name,Map<String,Object> values) {
        try {
            Files.createDirectories(directory);
            var node=JSON.createObjectNode().put("event",name).put("attemptId",a.attemptId()).put("generation",a.generation()).put("at",Instant.now().toString());
            values.forEach((k,v)->node.put(k,(Boolean)v));
            Files.writeString(directory.resolve(a.key()+"."+a.generation()+".events.jsonl"),JSON.writeValueAsString(node)+"\n",StandardOpenOption.CREATE,StandardOpenOption.APPEND);
        } catch(Exception ignored) { throw error(503,"LOCAL_OBSERVATION_UNAVAILABLE"); }
    }
}
