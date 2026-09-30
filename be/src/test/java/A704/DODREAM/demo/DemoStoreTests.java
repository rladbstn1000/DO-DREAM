package A704.DODREAM.demo;

import A704.DODREAM.auth.exception.AuthException;
import A704.DODREAM.authorization.AuthorizationPolicy;
import A704.DODREAM.indexing.*;
import A704.DODREAM.user.entity.*;
import jakarta.persistence.*;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

/** Store boundaries: actual concurrency/DB uniqueness are additionally verified through local HTTP. */
class DemoStoreTests {
    EntityManager em=mock(EntityManager.class);
    AuthorizationPolicy policy=mock(AuthorizationPolicy.class);
    IndexingStore indexing=mock(IndexingStore.class);
    LocalDemoStore store=new LocalDemoStore(em,policy,indexing);
    DemoCatalog catalog=new DemoCatalog(DemoManifest.VERSION,10,20);
    @BeforeEach @SuppressWarnings("unchecked") void setup() {
        when(em.find(DemoCatalog.class,DemoManifest.VERSION)).thenReturn(catalog);
        when(em.find(DemoCatalog.class,DemoManifest.VERSION,LockModeType.PESSIMISTIC_WRITE)).thenReturn(catalog);
        var query=mock(TypedQuery.class);when(em.createQuery(anyString(),eq(DemoSample.class))).thenReturn(query);
        when(query.setParameter(anyString(),any())).thenReturn(query);
        var first=new DemoSample("water-v1",DemoManifest.VERSION,30);first.materialId=40L;
        var second=new DemoSample("recycling-v1",DemoManifest.VERSION,31);second.materialId=41L;
        when(query.getResultList()).thenReturn(List.of(first,second));
        when(indexing.materialSummaries(10L,List.of(40L,41L))).thenReturn(Map.of(40L,new IndexingSummary("job","SUCCEEDED",1,true,true,false,1),41L,new IndexingSummary("job2","SUCCEEDED",1,true,true,false,1)));
    }
    @Test void exhaustedCatalogRejectsBeforeCreatingUserOrShare() {
        catalog.visitorCount=100;
        var e=assertThrows(AuthException.class,()->store.start("new-visitor",100));
        assertEquals("DEMO_CAPACITY_REACHED",e.code());assertEquals(429,e.status().value());
        verify(em).find(DemoCatalog.class,DemoManifest.VERSION,LockModeType.PESSIMISTIC_WRITE);
        verify(em,never()).persist(any());assertEquals(100,catalog.visitorCount);
    }
    @Test void concurrentStartLeaseRejectsBeforeReadinessOrSessionIssuance() {
        var visitor=new DemoVisitor("same",User.create("synthetic",Role.STUDENT),DemoManifest.VERSION);visitor.startingUntil=Instant.now().plusSeconds(20);
        when(em.find(DemoVisitor.class,"same",LockModeType.PESSIMISTIC_WRITE)).thenReturn(visitor);
        assertEquals("DEMO_START_IN_PROGRESS",assertThrows(AuthException.class,()->store.start("same",100)).code());
        verifyNoInteractions(indexing);verify(em,never()).persist(any());
    }
    @Test void notReadableStopsAllocationEvenWhenPublished() {
        when(indexing.materialSummaries(anyLong(),anyList())).thenReturn(Map.of(40L,IndexingSummary.none(),41L,IndexingSummary.none()));
        assertEquals("DEMO_NOT_READY",assertThrows(AuthException.class,()->store.start("new",100)).code());
        verify(em,never()).persist(any());assertEquals(0,catalog.visitorCount);
    }
    @Test void returningVisitorKeepsSameIdentityAndStillChecksCurrentShare() throws Exception {
        var user=User.create("returning",Role.STUDENT);var id=User.class.getDeclaredField("id");id.setAccessible(true);id.set(user,70L);
        var visitor=new DemoVisitor("same",user,DemoManifest.VERSION);
        when(em.find(DemoVisitor.class,"same",LockModeType.PESSIMISTIC_WRITE)).thenReturn(visitor);
        assertSame(user,store.start("same",100));verify(em,never()).persist(any());assertEquals(0,catalog.visitorCount);
        verify(policy).studentMaterial(70L,40L);verify(policy).studentMaterial(70L,41L);
        assertTrue(visitor.startingUntil.isAfter(Instant.now()));
    }
    @Test void returningVisitorCannotRestoreRevokedShareByStartingAgain() throws Exception {
        var user=User.create("revoked",Role.STUDENT);var id=User.class.getDeclaredField("id");id.setAccessible(true);id.set(user,70L);
        when(em.find(DemoVisitor.class,"same",LockModeType.PESSIMISTIC_WRITE)).thenReturn(new DemoVisitor("same",user,DemoManifest.VERSION));
        when(policy.studentMaterial(70L,40L)).thenThrow(AuthorizationPolicy.hidden());
        assertThrows(A704.DODREAM.authorization.AuthorizationFailure.class,()->store.start("same",100));verify(em,never()).persist(any());
    }
}
