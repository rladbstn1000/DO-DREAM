package A704.DODREAM.demo;

import A704.DODREAM.auth.service.AuthSessionService;
import A704.DODREAM.file.entity.UploadedFile;
import A704.DODREAM.indexing.*;
import A704.DODREAM.user.entity.*;
import jakarta.persistence.*;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.orm.jpa.EntityManagerHolder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

/** Real JPA/MySQL and local object storage. Only catalog allocation is an isolated test fixture. */
@SpringBootTest @ActiveProfiles("local")
class DemoPreparationBoundaryTests {
    @Autowired EntityManager em;
    @Autowired EntityManagerFactory factory;
    @Autowired PlatformTransactionManager transactions;
    @Autowired JdbcTemplate db;
    @Autowired IndexingStore ledger;
    @Autowired IndexingService indexing;
    @Autowired IndexingLocalHooks hooks;
    LocalDemoStore catalog;
    TransactionTemplate tx;
    long owner;
    List<LocalDemoStore.SampleView> samples;
    Map<String,Long> published;

    @BeforeEach void fixture() {
        tx=new TransactionTemplate(transactions);catalog=mock(LocalDemoStore.class);
        samples=new ArrayList<>();published=new HashMap<>();
        tx.executeWithoutResult(status->{
            var teacher=User.create("DEMO preparation boundary "+UUID.randomUUID(),Role.TEACHER);
            em.persist(teacher);em.flush();owner=teacher.getId();
            for(var sample:DemoManifest.SAMPLES) {
                var file=UploadedFile.builder().uploaderId(owner).originalFileName("demo-boundary-"+sample.key()+".json")
                    .s3Bucket("local-synthetic-fixtures").contentType("application/json").fileType("application/json").fileSize(0L).build();
                em.persist(file);em.flush();samples.add(new LocalDemoStore.SampleView(sample.key(),file.getId(),null));
            }
        });
        // These real fixture transactions reproduce the request OSIV connection
        // retention that previously caused INDEXING_TRANSACTION_BOUNDARY 503.
        when(catalog.reservePreparation(owner)).thenAnswer(call->tx.execute(status->{
            em.createNativeQuery("SELECT 1").getSingleResult();return List.copyOf(samples);
        }));
        doAnswer(call->{
            tx.executeWithoutResult(status->em.createNativeQuery("SELECT 1").getSingleResult());
            published.put(call.getArgument(1),call.getArgument(2));return null;
        }).when(catalog).prepared(eq(owner),anyString(),anyLong());
        doAnswer(call->{tx.executeWithoutResult(status->em.createNativeQuery("SELECT 1").getSingleResult());return null;})
            .when(catalog).finishPreparation(owner);
        when(catalog.catalog()).thenAnswer(call->new LocalDemoStore.CatalogView(owner,0,0,samples.stream()
            .map(sample->new LocalDemoStore.SampleView(sample.key(),sample.fileId(),published.get(sample.key()))).toList()));
    }
    LocalDemoService service(IndexingService publisher) {
        return new LocalDemoService(catalog,ledger,publisher,mock(AuthSessionService.class),mock(PasswordEncoder.class),factory,"unused-test-secret",100);
    }
    @Test void preparationReleasesFixtureConnectionsBeforeBothRealObjectWritesAndRestoresOsiv() {
        var view=factory.createEntityManager();var holder=new EntityManagerHolder(view);
        TransactionSynchronizationManager.bindResource(factory,holder);
        try {
            assertTrue(service(indexing).prepare(owner).enabled());
            assertEquals(2,published.size());
            for(var sample:samples) {
                assertNotNull(ledger.prepareFile(owner,sample.fileId(),null).jsonKey());
                assertEquals("QUEUED",ledger.resource(owner,"PDF",sample.fileId()).state());
                assertEquals("QUEUED",ledger.resource(owner,"MATERIAL",published.get(sample.key())).state());
            }
            assertSame(holder,TransactionSynchronizationManager.getResource(factory));
            assertFalse(view.unwrap(org.hibernate.engine.spi.SessionImplementor.class).getJdbcCoordinator().getLogicalConnection().isPhysicallyConnected());
            assertDoesNotThrow(()->hooks.boundary(samples.get(0).fileId(),false));
            verify(catalog).finishPreparation(owner);
        } finally {TransactionSynchronizationManager.unbindResource(factory);view.close();}
    }
    @Test void failedPublicationStillFinishesLeaseAndRestoresRequestEntityManager() {
        var publisher=mock(IndexingService.class);
        when(publisher.completeInitial(eq(owner),anyLong(),anyMap())).thenThrow(new IndexingFailure(503,"SYNTHETIC_PROVIDER_FAILURE"));
        var view=factory.createEntityManager();var holder=new EntityManagerHolder(view);
        TransactionSynchronizationManager.bindResource(factory,holder);
        try {
            assertEquals("SYNTHETIC_PROVIDER_FAILURE",assertThrows(IndexingFailure.class,()->service(publisher).prepare(owner)).code());
            verify(catalog).finishPreparation(owner);assertSame(holder,TransactionSynchronizationManager.getResource(factory));
            assertFalse(view.unwrap(org.hibernate.engine.spi.SessionImplementor.class).getJdbcCoordinator().getLogicalConnection().isPhysicallyConnected());
        } finally {TransactionSynchronizationManager.unbindResource(factory);view.close();}
    }
    @Test void activeCallerTransactionIsRejectedWithoutSuspendingItsConnectionOrPublishing() {
        tx.executeWithoutResult(status->{
            assertEquals("INDEXING_TRANSACTION_BOUNDARY",assertThrows(IndexingFailure.class,()->service(indexing).prepare(owner)).code());
            verify(catalog,never()).reservePreparation(anyLong());
        });
    }
}
