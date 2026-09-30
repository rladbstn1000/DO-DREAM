package A704.DODREAM.indexing;

import jakarta.persistence.EntityManagerFactory;
import java.nio.file.*;
import java.time.Instant;
import java.util.Map;
import javax.sql.DataSource;
import org.springframework.core.env.*;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/** Faults require the local profile AND an exact dedicated synthetic fixture classification. */
@Component
public class IndexingLocalHooks {
    private final boolean local;
    private final Path directory;
    private final DataSource dataSource;
    private final EntityManagerFactory factory;
    public IndexingLocalHooks(Environment environment,DataSource dataSource,EntityManagerFactory factory) {
        this.local=environment.acceptsProfiles(Profiles.of("local")); this.dataSource=dataSource; this.factory=factory;
        directory=Path.of(environment.getProperty("LOCAL_DATA_DIR","/app/local-data"),"indexing-controls");
    }
    private boolean mode(long fileId,boolean synthetic,String mode) {
        if(!local || !synthetic) return false;
        Path path=directory.resolve("file-"+fileId+".json");
        try { return !Files.isSymbolicLink(path) && Files.size(path)<=4096 && mode.equals(IndexingSource.JSON.readTree(Files.readString(path)).path("mode").textValue()); }
        catch(Exception ignored) { return false; }
    }
    public void boundary(long fileId,boolean synthetic) {
        boolean active=TransactionSynchronizationManager.isActualTransactionActive();
        boolean bound=TransactionSynchronizationManager.hasResource(dataSource);
        Object resource=TransactionSynchronizationManager.getResource(factory);
        boolean physical=resource instanceof org.springframework.orm.jpa.EntityManagerHolder holder
            && holder.getEntityManager().isOpen()
            && holder.getEntityManager().unwrap(org.hibernate.engine.spi.SessionImplementor.class)
                .getJdbcCoordinator().getLogicalConnection().isPhysicallyConnected();
        if(local && synthetic) event(fileId,"storage_boundary",Map.of("transactionActive",active,"connectionBound",bound,"hibernateConnectionHeld",physical));
        if(active || bound || physical) throw new IndexingFailure(503,"INDEXING_TRANSACTION_BOUNDARY");
    }
    public void rollback(long fileId,boolean synthetic) {
        if(mode(fileId,synthetic,"rollback")) {
            event(fileId,"rollback",Map.of());
            throw new IndexingFailure(503,"LOCAL_INDEXING_ROLLBACK");
        }
    }
    public void prepared(long fileId,boolean synthetic) {
        if(mode(fileId,synthetic,"fail_after_object")) throw new IndexingFailure(503,"LOCAL_INDEXING_OBJECT_PREPARED");
    }
    public void committed(long fileId,boolean synthetic) {
        if(mode(fileId,synthetic,"after_commit")) {
            event(fileId,"after_commit",Map.of());
            long deadline=System.nanoTime()+45_000_000_000L;
            Path release=directory.resolve("file-"+fileId+".release");
            try { while(System.nanoTime()<deadline && !Files.exists(release)) Thread.sleep(100); }
            catch(InterruptedException interrupted) { Thread.currentThread().interrupt(); throw new IndexingFailure(503,"LOCAL_INDEXING_INTERRUPTED"); }
        }
        if(mode(fileId,synthetic,"after_commit_response_lost")) throw new IndexingFailure(503,"LOCAL_INDEXING_RESPONSE_LOST");
    }
    private void event(long fileId,String event,Map<String,Boolean> values) {
        try {
            Files.createDirectories(directory);
            var node=IndexingSource.JSON.createObjectNode().put("event",event).put("fileId",fileId).put("at",Instant.now().toString());
            values.forEach(node::put);
            Files.writeString(directory.resolve("file-"+fileId+".events.jsonl"),IndexingSource.JSON.writeValueAsString(node)+"\n",StandardOpenOption.CREATE,StandardOpenOption.APPEND);
        } catch(Exception failure) { throw new IndexingFailure(503,"LOCAL_INDEXING_OBSERVATION_UNAVAILABLE"); }
    }
}
