package A704.DODREAM.quiz.grading;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.core.env.MapPropertySource;
import org.springframework.web.reactive.function.client.WebClient;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
class GradingWiringTests {
    @Test void boundaryDenialBeforeHttpIsKnownFailureWithZeroProviderCalls() throws Exception {
        var store=mock(GradingStore.class);var hooks=mock(GradingLocalHooks.class);
        var at=java.time.LocalDateTime.now();
        String id="00000000-0000-0000-0000-000000000001";
        var attempt=new GradingContract.Attempt(1,id,21,73,id,"fingerprint","PROCESSING",1,at.plusSeconds(30),null,at,null);
        var execution=new GradingContract.Execution(attempt,"synthetic-capability",java.util.List.of());
        when(store.accept(org.mockito.ArgumentMatchers.eq(21L),org.mockito.ArgumentMatchers.eq(73L),org.mockito.ArgumentMatchers.any())).thenReturn(attempt);
        when(store.claim(21,73,id,null,true)).thenReturn(execution);
        when(store.localFixture(attempt)).thenReturn(true);
        when(store.dispatch(execution)).thenReturn(true);
        doThrow(GradingContract.error(503,"GRADING_TRANSACTION_BOUNDARY")).when(hooks).boundary(attempt,true);
        var failed=new GradingContract.Attempt(1,id,21,73,id,"fingerprint","FAILED",1,at,null,at,"GRADING_TRANSACTION_BOUNDARY");
        when(store.view(21,73,id)).thenReturn(new GradingContract.View(failed,java.util.List.of()));
        var calls=new java.util.concurrent.atomic.AtomicInteger();
        var client=WebClient.builder().exchangeFunction(request->{calls.incrementAndGet();return reactor.core.publisher.Mono.error(new IllegalStateException("provider must not run"));}).build();
        var service=new GradingAttemptService(store,hooks,client,"http://127.0.0.1:9");
        var body=GradingContract.JSON.readTree("{\"answers\":[{\"quizId\":1,\"version\":0,\"answer\":\"x\"}]}");
        assertEquals(502,service.submit(21,73,id,body,"synthetic-token").getStatusCode().value());
        verify(store).fail(execution,"FAILED","GRADING_TRANSACTION_BOUNDARY");
        assertEquals(0,calls.get());
    }
    @Test void gradingUsesApprovedWebClientWithOtherClientBeansPresent() {
        try(var context=new AnnotationConfigApplicationContext()) {
            context.getEnvironment().getPropertySources().addFirst(new MapPropertySource("synthetic",Map.of("fastapi.url","http://127.0.0.1:9")));
            context.registerBean("webClient",WebClient.class,()->WebClient.builder().build());
            context.registerBean("branchWebClient",WebClient.class,()->mock(WebClient.class));
            context.registerBean(GradingStore.class,()->mock(GradingStore.class));
            context.registerBean(GradingLocalHooks.class,()->mock(GradingLocalHooks.class));
            context.register(GradingAttemptService.class);
            context.refresh();
            assertNotNull(context.getBean(GradingAttemptService.class));
            verifyNoInteractions(context.getBean("branchWebClient",WebClient.class));
        }
    }
}
