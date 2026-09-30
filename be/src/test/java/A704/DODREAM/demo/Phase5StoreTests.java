package A704.DODREAM.demo;

import A704.DODREAM.authorization.*;
import A704.DODREAM.indexing.IndexingFailure;
import A704.DODREAM.material.entity.Material;
import jakarta.persistence.*;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.jdbc.core.JdbcTemplate;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class Phase5StoreTests {
    EntityManager em=mock(EntityManager.class);
    AuthorizationPolicy policy=mock(AuthorizationPolicy.class);
    JdbcTemplate db=mock(JdbcTemplate.class);
    Phase5Store store=new Phase5Store(em,policy,db);
    DemoCatalog catalog=new DemoCatalog(DemoManifest.VERSION,10,20);
    @BeforeEach void setup(){when(em.find(DemoCatalog.class,DemoManifest.VERSION,LockModeType.PESSIMISTIC_WRITE)).thenReturn(catalog);}
    @Test void otherTeacherCannotAllocateFixtures() {
        assertThrows(AuthorizationFailure.class,()->store.reserve(11,null));verify(em,never()).persist(any());verifyNoInteractions(db);
    }
    @Test void existingPreparationLeaseDeniesBeforeAllocation() {
        catalog.preparingUntil=Instant.now().plusSeconds(60);
        assertEquals("DEMO_PREPARATION_IN_PROGRESS",assertThrows(IndexingFailure.class,()->store.reserve(10,null)).code());
        verify(em,never()).persist(any());verifyNoInteractions(db);
    }
    @Test @SuppressWarnings("unchecked") void nonCohortStudentIsDeniedBeforeFixturesOrShares() {
        TypedQuery<Long> query=mock(TypedQuery.class);
        when(em.createQuery(anyString(),eq(Long.class))).thenReturn(query);
        when(query.setParameter(anyString(),any())).thenReturn(query);when(query.getSingleResult()).thenReturn(0L);
        assertThrows(AuthorizationFailure.class,()->store.reserve(10,30L));verify(em,never()).persist(any());verifyNoInteractions(db);
    }
    @Test void editedExistingMaterialFailsInsteadOfOverwriting() {
        var sample=Phase5Manifest.SAMPLES.get(0);var row=new DemoSample(sample.sampleKey(),Phase5Manifest.VERSION,40);row.materialId=50L;
        when(em.find(DemoSample.class,sample.sampleKey())).thenReturn(row);
        when(policy.owned(10L,50L)).thenReturn(Material.builder().title("teacher edited title").build());
        when(db.queryForList(anyString(),eq(String.class),eq(50L))).thenReturn(List.of(sample.sourceHash()));
        assertEquals("PHASE5_SOURCE_CHANGED",assertThrows(IndexingFailure.class,()->store.reserve(10,null)).code());
        verify(em,never()).persist(any());
    }
}
