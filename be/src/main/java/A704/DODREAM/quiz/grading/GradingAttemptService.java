package A704.DODREAM.quiz.grading;

import com.fasterxml.jackson.databind.JsonNode;
import io.netty.channel.ChannelOption;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.reactive.function.client.*;
import reactor.netty.http.client.HttpClient;
import java.time.Duration;
import java.util.*;
import static A704.DODREAM.quiz.grading.GradingContract.*;

@Service
public class GradingAttemptService {
    private final GradingStore store;
    private final GradingLocalHooks hooks;
    private final WebClient client;
    private final String url;
    public GradingAttemptService(GradingStore store,GradingLocalHooks hooks,@org.springframework.beans.factory.annotation.Qualifier("webClient") WebClient client,@Value("${fastapi.url}") String url) {
        this.store=store; this.hooks=hooks; this.url=url;
        this.client=client.mutate().clientConnector(new ReactorClientHttpConnector(HttpClient.create().disableRetry(true)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS,2000).responseTimeout(Duration.ofSeconds(12))))
            .codecs(c->c.defaultCodecs().maxInMemorySize(2*1024*1024)).build();
    }
    @Transactional(propagation=Propagation.NOT_SUPPORTED)
    public ResponseEntity<?> submit(long student,long material,String key,JsonNode body,String token) {
        store.authorize(student,material);
        Submission submission=parse(key,material,body);
        Attempt a=store.accept(student,material,submission);
        Execution execution=store.claim(student,material,a.attemptId(),null,true);
        if(execution!=null) execute(execution,token);
        return response(store.view(student,material,a.attemptId()));
    }
    @Transactional(propagation=Propagation.NOT_SUPPORTED)
    public ResponseEntity<?> status(long student,long material,String id) { return response(store.view(student,material,id)); }
    @Transactional(propagation=Propagation.NOT_SUPPORTED)
    public ResponseEntity<?> retry(long student,long material,String id,JsonNode input,String token) {
        uuid(id);
        store.authorize(student,material);
        Retry request=GradingContract.retry(input);
        Execution execution=store.claim(student,material,id,request,false);
        if(execution!=null) execute(execution,token);
        return response(store.view(student,material,id));
    }
    private void execute(Execution e,String token) {
        boolean dispatched=false;
        boolean enabled=false;
        try {
            enabled=store.localFixture(e.attempt());
            hooks.gate(e.attempt(),"before_dispatch",enabled);
            if(!store.dispatch(e)) return;
            hooks.boundary(e.attempt(),enabled);
            dispatched=true;
            // The only outbound call. Its subscription happens after every database transaction ended.
            String raw=client.post().uri(url+"/rag/quiz/grade-batch").header("Authorization",token)
                .bodyValue(Map.of("attempt_id",e.attempt().attemptId(),"execution_generation",e.attempt().generation(),"execution_token",e.capability()))
                .retrieve().bodyToMono(String.class).timeout(Duration.ofSeconds(15)).block(Duration.ofSeconds(16));
            var results=provider(raw,e.items());
            hooks.gate(e.attempt(),"after_response",enabled);
            store.complete(e,results);
        } catch(GradingFailure failure) {
            store.fail(e,failure.code.equals("INVALID_PROVIDER_RESPONSE")?"FAILED":dispatched?"UNKNOWN":"FAILED",failure.code);
        } catch(WebClientResponseException response) {
            // A completed HTTP failure contains no accepted grades. Do not persist response bodies.
            store.fail(e,response.getStatusCode().value()==504?"UNKNOWN":"FAILED",response.getStatusCode().value()==504?"PROVIDER_OUTCOME_UNKNOWN":"PROVIDER_HTTP_ERROR");
        } catch(RuntimeException unknown) {
            store.fail(e,dispatched?"UNKNOWN":"FAILED",dispatched?"EXECUTION_OUTCOME_UNKNOWN":"BEFORE_DISPATCH_FAILURE");
        }
        hooks.afterCommit(e.attempt(),enabled);
    }
    private ResponseEntity<?> response(View view) {
        Attempt a=view.attempt();
        int status=switch(a.state()) {case "SUCCEEDED"->200; case "READY","PROCESSING"->202; case "FAILED"->502; case "UNKNOWN"->503; default->409;};
        Object body;
        if(status==200) body=view.results();
        else {
            Map<String,Object> state=new LinkedHashMap<>(); state.put("attemptId",a.attemptId()); state.put("state",a.state());
            state.put("generation",a.generation()); state.put("failureCode",a.failureCode());
            state.put("retryable",a.generation()<3 && Set.of("READY","FAILED","UNKNOWN").contains(a.state()));
            state.put("deadlineAt",a.deadline()); body=state;
        }
        return ResponseEntity.status(status).header("X-Grading-Attempt-Id",a.attemptId()).header("X-Grading-State",a.state()).body(body);
    }
}
