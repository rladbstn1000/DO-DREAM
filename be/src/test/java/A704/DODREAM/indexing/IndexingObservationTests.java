package A704.DODREAM.indexing;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import javax.sql.DataSource;
import org.hibernate.engine.spi.SessionImplementor;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.env.MockEnvironment;
import org.springframework.orm.jpa.EntityManagerHolder;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

/** No server, database, JDBC connection acquisition or network is used by these observation tests. */
class IndexingObservationTests {
    @TempDir Path directory;
    final DataSource dataSource=mock(DataSource.class);
    final EntityManagerFactory factory=mock(EntityManagerFactory.class);

    IndexingLocalHooks hooks(boolean local) {
        var environment=new MockEnvironment().withProperty("LOCAL_DATA_DIR",directory.toString());
        if(local) environment.setActiveProfiles("local");
        return new IndexingLocalHooks(environment,dataSource,factory);
    }
    EntityManagerHolder holder(boolean physical) {
        EntityManager em=mock(EntityManager.class);
        SessionImplementor session=mock(SessionImplementor.class,RETURNS_DEEP_STUBS);
        when(em.isOpen()).thenReturn(true);
        when(em.unwrap(SessionImplementor.class)).thenReturn(session);
        when(session.getJdbcCoordinator().getLogicalConnection().isPhysicallyConnected()).thenReturn(physical);
        return new EntityManagerHolder(em);
    }
    List<com.fasterxml.jackson.databind.JsonNode> events() throws Exception {
        try(var files=Files.list(directory.resolve("indexing-controls"))) {
            var lines=new java.util.ArrayList<com.fasterxml.jackson.databind.JsonNode>();
            for(Path path:files.toList()) for(String line:Files.readAllLines(path)) lines.add(IndexingSource.JSON.readTree(line));
            return lines;
        }
    }
    @AfterEach void clearThreadState() {
        TransactionSynchronizationManager.unbindResourceIfPossible(factory);
        TransactionSynchronizationManager.unbindResourceIfPossible(dataSource);
        TransactionSynchronizationManager.clear();
    }

    @Test void readsExistingConnectionStateWithoutBorrowingConnection() throws Exception {
        var hooks=hooks(true);
        var request=holder(true);
        TransactionSynchronizationManager.bindResource(factory,request);
        try(var ignored=hooks.observation()) {
            hooks.observe(IndexingLocalHooks.Stage.CONTROLLER_PERMISSION_AFTER);
            TransactionSynchronizationManager.unbindResource(factory);
            hooks.observe(IndexingLocalHooks.Stage.STORE_AFTER_DETACH,request);
        }
        var records=events();
        var before=records.stream().filter(n->n.path("stage").asText().equals("CONTROLLER_PERMISSION_AFTER")).findFirst().orElseThrow();
        var detached=records.stream().filter(n->n.path("stage").asText().equals("STORE_AFTER_DETACH")).findFirst().orElseThrow();
        assertTrue(before.path("requestEntityManagerPresent").asBoolean());
        assertTrue(before.path("physicalConnectionHeld").asBoolean());
        assertFalse(before.path("transactionActive").asBoolean());
        assertFalse(before.path("synchronizationActive").asBoolean());
        assertFalse(before.path("dataSourceBound").asBoolean());
        assertFalse(detached.path("requestEntityManagerPresent").asBoolean());
        assertTrue(detached.path("detachedPhysicalConnectionHeld").asBoolean());
        verifyNoInteractions(dataSource);
        verify(request.getEntityManager(),never()).close();
        verify(request.getEntityManager(),never()).clear();
        verify(request.getEntityManager().unwrap(SessionImplementor.class).getJdbcCoordinator().getLogicalConnection(),never()).getPhysicalConnection();
    }
    @Test void scopeClosesOnExceptionAndDoesNotLeakToNextRequestOnSameThread() throws Exception {
        var hooks=hooks(true);
        assertThrows(IllegalStateException.class,()->{
            try(var ignored=hooks.observation()) { throw new IllegalStateException("synthetic"); }
        });
        hooks.observe(IndexingLocalHooks.Stage.INPUT_BEFORE);
        try(var ignored=hooks.observation()) { hooks.observe(IndexingLocalHooks.Stage.INPUT_AFTER); }
        var records=events();
        assertEquals(5,records.size());
        assertEquals(2,records.stream().map(n->n.path("correlationId").asText()).distinct().count());
        assertTrue(records.stream().noneMatch(n->n.path("stage").asText().equals("INPUT_BEFORE")));
        verifyNoInteractions(dataSource,factory);
    }
    @Test void observationFailureRestoresThreadScope() throws Exception {
        Files.writeString(directory.resolve("indexing-controls"),"synthetic path collision");
        var hooks=hooks(true);
        assertEquals("LOCAL_INDEXING_OBSERVATION_UNAVAILABLE",assertThrows(IndexingFailure.class,hooks::observation).code());
        assertDoesNotThrow(()->hooks.observe(IndexingLocalHooks.Stage.INPUT_AFTER));
        verifyNoInteractions(dataSource,factory);
    }
    @Test void nonLocalProfileCreatesNoObservationAndNeverQueriesConnectionState() {
        var hooks=hooks(false);
        var request=holder(true);
        TransactionSynchronizationManager.bindResource(factory,request);
        clearInvocations(request.getEntityManager());
        try(var ignored=hooks.observation()) { hooks.observe(IndexingLocalHooks.Stage.INPUT_BEFORE); }
        assertFalse(Files.exists(directory.resolve("indexing-controls")));
        verifyNoInteractions(dataSource,factory,request.getEntityManager());
    }
    @Test void guardStillRejectsActualTransactionDataSourceBindingAndPhysicalConnection() {
        var hooks=hooks(true);
        TransactionSynchronizationManager.setActualTransactionActive(true);
        assertEquals("INDEXING_TRANSACTION_BOUNDARY",assertThrows(IndexingFailure.class,()->hooks.boundary(0,false)).code());
        TransactionSynchronizationManager.setActualTransactionActive(false);
        TransactionSynchronizationManager.bindResource(dataSource,new Object());
        assertEquals("INDEXING_TRANSACTION_BOUNDARY",assertThrows(IndexingFailure.class,()->hooks.boundary(0,false)).code());
        TransactionSynchronizationManager.unbindResource(dataSource);
        TransactionSynchronizationManager.bindResource(factory,holder(true));
        assertEquals("INDEXING_TRANSACTION_BOUNDARY",assertThrows(IndexingFailure.class,()->hooks.boundary(0,false)).code());
        TransactionSynchronizationManager.unbindResource(factory);
        TransactionSynchronizationManager.bindResource(factory,holder(false));
        assertDoesNotThrow(()->hooks.boundary(0,false));
        verifyNoInteractions(dataSource,factory);
    }
}
