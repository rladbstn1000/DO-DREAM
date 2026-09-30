package A704.DODREAM.demo;

import A704.DODREAM.indexing.*;
import jakarta.persistence.EntityManagerFactory;
import java.util.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/** Offline fixture preparation; this endpoint never calls an AI provider. */
@Service @Profile("local") @ConditionalOnProperty(name={"LOCAL_DEMO_ENABLED","LOCAL_PHASE5_ENABLED"},havingValue="true")
public class Phase5Service {
    private final Phase5Store store;
    private final IndexingStore ledger;
    private final IndexingService indexing;
    private final EntityManagerFactory factory;
    public Phase5Service(Phase5Store store,IndexingStore ledger,IndexingService indexing,EntityManagerFactory factory) {
        this.store=store;this.ledger=ledger;this.indexing=indexing;this.factory=factory;
    }
    public record Result(String status,String fixture_version,String resource_sha256,List<Phase5Store.Prepared> materials) {}
    public Result prepare(long actor,Long studentId) {
        if(TransactionSynchronizationManager.isActualTransactionActive())throw new IndexingFailure(503,"INDEXING_TRANSACTION_BOUNDARY");
        Object holder=TransactionSynchronizationManager.unbindResourceIfPossible(factory);
        try {return prepareDetached(actor,studentId);}
        finally {if(holder!=null)TransactionSynchronizationManager.bindResource(factory,holder);}
    }
    private Result prepareDetached(long actor,Long studentId) {
        var reserved=store.reserve(actor,studentId);
        try {
            var result=new ArrayList<Phase5Store.Prepared>();
            for(var row:reserved) {
                var sample=Phase5Manifest.SAMPLES.stream().filter(value->value.key().equals(row.key())).findFirst().orElseThrow();
                Long id=row.materialId();
                if(id==null) {
                    if(ledger.prepareFile(actor,row.fileId(),null).jsonKey()==null)indexing.completeInitial(actor,row.fileId(),sample.initial());
                    id=indexing.publish(actor,row.fileId(),sample.publication()).materialId();
                    store.prepared(actor,sample,id);
                }
                if(!store.hasLiveJob(actor,id,sample))indexing.request(actor,"MATERIAL",id,Phase5Manifest.SPEC);
                result.add(store.result(actor,studentId,id,sample));
            }
            return new Result("PASS",Phase5Manifest.VERSION,Phase5Manifest.RESOURCE_SHA256,List.copyOf(result));
        } finally {store.finish(actor);}
    }
}
