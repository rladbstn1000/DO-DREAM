package A704.DODREAM.indexing;

import jakarta.persistence.EntityManagerFactory;
import java.nio.file.*;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
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
    private final ThreadLocal<String> observationId=new ThreadLocal<>();
    public enum Stage {
        REQUEST_BEGIN, CONTROLLER_PERMISSION_BEFORE, CONTROLLER_PERMISSION_AFTER,
        INPUT_BEFORE, INPUT_AFTER, SERVICE_PERMISSION_BEFORE, SERVICE_PERMISSION_AFTER,
        STORE_BEFORE_DETACH, STORE_AFTER_DETACH, STORE_BEFORE_RESTORE, STORE_AFTER_RESTORE,
        OBJECT_WRITE_BEFORE, FILE_RECORD_BEFORE, FILE_RECORD_AFTER, PARSE_BEFORE,
        INITIAL_INDEX_BEFORE, INITIAL_INDEX_AFTER, STORAGE_BOUNDARY, REQUEST_END
    }
    public IndexingLocalHooks(Environment environment,DataSource dataSource,EntityManagerFactory factory) {
        this.local=environment.acceptsProfiles(Profiles.of("local")); this.dataSource=dataSource; this.factory=factory;
        directory=Path.of(environment.getProperty("LOCAL_DATA_DIR","/app/local-data"),"indexing-controls");
    }
    /** Local-only diagnostics contain no request input, identity, token, path or URL. */
    public Observation observation() {
        String previous=observationId.get();
        Observation scope=new Observation(previous);
        if(local) {
            observationId.set(UUID.randomUUID().toString());
            try { observe(Stage.REQUEST_BEGIN); }
            catch(RuntimeException failure) { scope.restore(); throw failure; }
        }
        return scope;
    }
    public final class Observation implements AutoCloseable {
        private final String previous;
        private Observation(String previous) { this.previous=previous; }
        @Override public void close() {
            try { observe(Stage.REQUEST_END); }
            finally { restore(); }
        }
        private void restore() { if(previous==null) observationId.remove(); else observationId.set(previous); }
    }
    public void observe(Stage stage) { observe(stage,null); }
    public void observe(Stage stage,Object detached) {
        String correlation=observationId.get();
        if(!local || correlation==null) return;
        Object request=TransactionSynchronizationManager.getResource(factory);
        var node=IndexingSource.JSON.createObjectNode().put("correlationId",correlation)
            .put("stage",stage.name()).put("at",Instant.now().toString())
            .put("transactionActive",TransactionSynchronizationManager.isActualTransactionActive())
            .put("synchronizationActive",TransactionSynchronizationManager.isSynchronizationActive())
            .put("dataSourceBound",TransactionSynchronizationManager.hasResource(dataSource))
            .put("requestEntityManagerPresent",request instanceof org.springframework.orm.jpa.EntityManagerHolder)
            .put("physicalConnectionHeld",physicalConnectionHeld(request))
            .put("detachedEntityManagerPresent",detached instanceof org.springframework.orm.jpa.EntityManagerHolder)
            .put("detachedPhysicalConnectionHeld",physicalConnectionHeld(detached));
        try {
            Files.createDirectories(directory);
            Files.writeString(directory.resolve("request-"+correlation+".events.jsonl"),
                IndexingSource.JSON.writeValueAsString(node)+"\n",StandardOpenOption.CREATE,StandardOpenOption.APPEND);
        } catch(Exception failure) { throw new IndexingFailure(503,"LOCAL_INDEXING_OBSERVATION_UNAVAILABLE"); }
    }
    private boolean physicalConnectionHeld(Object resource) {
        // Inspect Hibernate's existing logical connection. Never borrow a connection to observe it.
        return resource instanceof org.springframework.orm.jpa.EntityManagerHolder holder
            && holder.getEntityManager().isOpen()
            && holder.getEntityManager().unwrap(org.hibernate.engine.spi.SessionImplementor.class)
                .getJdbcCoordinator().getLogicalConnection().isPhysicallyConnected();
    }
    private boolean mode(long fileId,boolean synthetic,String mode) {
        if(!local || !synthetic) return false;
        Path path=directory.resolve("file-"+fileId+".json");
        try { return !Files.isSymbolicLink(path) && Files.size(path)<=4096 && mode.equals(IndexingSource.JSON.readTree(Files.readString(path)).path("mode").textValue()); }
        catch(Exception ignored) { return false; }
    }
    public void boundary(long fileId,boolean synthetic) {
        observe(Stage.STORAGE_BOUNDARY);
        boolean active=TransactionSynchronizationManager.isActualTransactionActive();
        boolean bound=TransactionSynchronizationManager.hasResource(dataSource);
        Object resource=TransactionSynchronizationManager.getResource(factory);
        boolean physical=physicalConnectionHeld(resource);
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
