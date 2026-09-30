package A704.DODREAM.demo;

import A704.DODREAM.indexing.*;
import jakarta.persistence.EntityManagerFactory;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class Phase5ServiceTests {
    Phase5Store store=mock(Phase5Store.class);
    IndexingStore ledger=mock(IndexingStore.class);
    IndexingService indexing=mock(IndexingService.class);
    EntityManagerFactory factory=mock(EntityManagerFactory.class);
    Phase5Service service=new Phase5Service(store,ledger,indexing,factory);
    @AfterEach void clear(){TransactionSynchronizationManager.setActualTransactionActive(false);TransactionSynchronizationManager.unbindResourceIfPossible(factory);}
    @Test void rejectsActualCallerTransactionBeforeExternalOrStoreWork() {
        TransactionSynchronizationManager.setActualTransactionActive(true);
        assertThrows(IndexingFailure.class,()->service.prepare(1,null));verifyNoInteractions(store,ledger,indexing);
    }
    @Test void existingLiveJobsReplayWithoutWritingObjectsOrRepublishing() {
        var sample=Phase5Manifest.SAMPLES.get(0);
        when(store.reserve(1,2L)).thenReturn(List.of(new Phase5Store.Reserved(sample.key(),10,20L)));
        when(store.hasLiveJob(1,20,sample)).thenReturn(true);
        when(store.result(1,2L,20,sample)).thenReturn(new Phase5Store.Prepared(sample.key(),20,List.of(1L,2L),1,sample.sourceHash(),Phase5Manifest.SPEC,"job",Map.of()));
        Object holder=new Object();TransactionSynchronizationManager.bindResource(factory,holder);
        var result=service.prepare(1,2L);
        assertEquals("PASS",result.status());assertSame(holder,TransactionSynchronizationManager.getResource(factory));
        verifyNoInteractions(indexing,ledger);verify(store).finish(1);
    }
    @Test void newMaterialsUseInitialPublicationThenRealLiveRequestAndReleaseLease() {
        var sample=Phase5Manifest.SAMPLES.get(0);
        when(store.reserve(1,null)).thenReturn(List.of(new Phase5Store.Reserved(sample.key(),10,null)));
        when(ledger.prepareFile(1,10,null)).thenReturn(new IndexingStore.FileView(10,1,"fixture",null,null,"local",null,false));
        when(indexing.publish(eq(1L),eq(10L),any())).thenReturn(new IndexingStore.Publication(20,"file","key",IndexingSummary.none()));
        when(store.result(1,null,20,sample)).thenReturn(new Phase5Store.Prepared(sample.key(),20,List.of(1L),1,sample.sourceHash(),Phase5Manifest.SPEC,"job",Map.of()));
        service.prepare(1,null);
        var ordered=inOrder(indexing,store);
        ordered.verify(store).reserve(1,null);ordered.verify(indexing).completeInitial(1,10,sample.initial());
        ordered.verify(indexing).publish(eq(1L),eq(10L),any());ordered.verify(store).prepared(1,sample,20);
        ordered.verify(store).hasLiveJob(1,20,sample);ordered.verify(indexing).request(1,"MATERIAL",20,Phase5Manifest.SPEC);
        ordered.verify(store).result(1,null,20,sample);ordered.verify(store).finish(1);
    }
}
