package A704.DODREAM.demo;

import A704.DODREAM.auth.service.AuthSessionService;
import A704.DODREAM.indexing.*;
import jakarta.persistence.EntityManagerFactory;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.core.annotation.Order;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service @Profile("local") @ConditionalOnProperty(name="LOCAL_DEMO_ENABLED",havingValue="true") @Order(30)
public class LocalDemoService implements ApplicationRunner {
    private final LocalDemoStore store;
    private final IndexingStore ledger;
    private final IndexingService indexing;
    private final AuthSessionService sessions;
    private final PasswordEncoder encoder;
    private final EntityManagerFactory factory;
    private final String password;
    private final int maximum;
    public LocalDemoService(LocalDemoStore store,IndexingStore ledger,IndexingService indexing,AuthSessionService sessions,PasswordEncoder encoder,EntityManagerFactory factory,
        @Value("${LOCAL_TEACHER_PASSWORD}") String password,@Value("${LOCAL_DEMO_MAX_VISITORS:100}") int maximum) {
        if(maximum<1 || maximum>1000)throw new IllegalArgumentException("Local demo visitor limit must be 1..1000");
        this.store=store;this.ledger=ledger;this.indexing=indexing;this.sessions=sessions;this.encoder=encoder;this.factory=factory;this.password=password;this.maximum=maximum;
    }
    @Override public void run(ApplicationArguments args) {store.initialize(password,encoder);}
    public record SampleStatus(String key,String title,String description,String source,String version,Long materialId,boolean readable,long sourceRevision) {}
    public record Configuration(boolean enabled,String mode,int visitorLimit,String fixtureVersion,boolean ready,List<SampleStatus> samples) {}
    public static Configuration disabled() {return new Configuration(false,"UNAVAILABLE",0,DemoManifest.VERSION,false,List.of());}
    public Configuration configuration() {
        var c=store.catalog();var byKey=new HashMap<String,LocalDemoStore.SampleView>();c.samples().forEach(s->byKey.put(s.key(),s));
        var statuses=new ArrayList<SampleStatus>();
        for(var sample:DemoManifest.SAMPLES) {
            var value=byKey.get(sample.key());Long id=value==null?null:value.materialId();
            var status=id==null?IndexingSummary.none():ledger.resource(c.teacherId(),"MATERIAL",id);
            statuses.add(new SampleStatus(sample.key(),sample.title(),sample.description(),DemoManifest.SOURCE,DemoManifest.VERSION,id,status.readable(),status.sourceRevision()));
        }
        return new Configuration(true,"LOCAL_DETERMINISTIC",maximum,DemoManifest.VERSION,statuses.stream().allMatch(SampleStatus::readable),statuses);
    }
    public Configuration prepare(long actor) {
        // Reuse the indexing/grading OSIV boundary: fixture transactions must own
        // and close their EntityManager before the real object-store calls.
        // Suspending an actual caller transaction would retain its DB connection.
        if(TransactionSynchronizationManager.isActualTransactionActive())
            throw new IndexingFailure(503,"INDEXING_TRANSACTION_BOUNDARY");
        Object holder=TransactionSynchronizationManager.unbindResourceIfPossible(factory);
        try {return prepareWithoutRequestEntityManager(actor);}
        finally {if(holder!=null)TransactionSynchronizationManager.bindResource(factory,holder);}
    }
    private Configuration prepareWithoutRequestEntityManager(long actor) {
        var samples=store.reservePreparation(actor);
        try {
            for(var sample:samples) {
                if(sample.materialId()!=null) continue;
                var manifest=DemoManifest.SAMPLES.stream().filter(s->s.key().equals(sample.key())).findFirst().orElseThrow();
                var file=ledger.prepareFile(actor,sample.fileId(),null);
                if(file.jsonKey()==null) indexing.completeInitial(actor,sample.fileId(),manifest.initial());
                var publication=indexing.publish(actor,sample.fileId(),manifest.publication());
                store.prepared(actor,sample.key(),publication.materialId());
            }
            return configuration();
        } finally {store.finishPreparation(actor);}
    }
    public AuthSessionService.Tokens start(String visitorHash) {
        var user=store.start(visitorHash,maximum);
        var tokens=sessions.login(user); // Actual Redis session. No DB transaction spans token issuance.
        store.issued(visitorHash);
        return tokens;
    }
    public boolean isDemo(long user) {return store.isDemo(user);}
    public Object preparation(long actor) {
        store.owner(actor);return Map.of("fixtureVersion",DemoManifest.VERSION,"teacherEmail",DemoManifest.TEACHER_EMAIL,
            "teacherId",store.catalog().teacherId(),"classroomId",store.catalog().classroomId(),"createdVisitors",store.catalog().visitors(),"samples",store.catalog().samples(),"counts",store.counts(actor),"configuration",configuration());
    }
}
