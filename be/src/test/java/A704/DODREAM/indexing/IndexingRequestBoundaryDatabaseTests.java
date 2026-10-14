package A704.DODREAM.indexing;

import A704.DODREAM.authorization.AuthorizationFailure;
import A704.DODREAM.authorization.AuthorizationPolicy;
import A704.DODREAM.auth.util.JwtUtil;
import A704.DODREAM.user.entity.Role;
import A704.DODREAM.user.entity.User;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;
import org.hibernate.engine.spi.SessionImplementor;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.core.Ordered;
import org.springframework.orm.jpa.EntityManagerHolder;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.filter.OncePerRequestFilter;
import static org.junit.jupiter.api.Assertions.*;

/** Real MySQL/JPA, no enclosing test transaction. Only two fresh users per class run are added. */
@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT,properties={
    "server.address=127.0.0.1", "server.tomcat.threads.max=1", "server.tomcat.threads.min-spare=1"
})
@ActiveProfiles("local")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@Import(IndexingRequestBoundaryDatabaseTests.HttpObservationConfiguration.class)
class IndexingRequestBoundaryDatabaseTests {
    @Autowired EntityManager em;
    @Autowired EntityManagerFactory factory;
    @Autowired PlatformTransactionManager transactions;
    @Autowired DataSource dataSource;
    @Autowired AuthorizationPolicy policy;
    @Autowired IndexingStore store;
    @Autowired IndexingLocalHooks hooks;
    @Autowired JwtUtil jwt;
    @Autowired CompletedRequests completedRequests;
    @LocalServerPort int port;
    long teacher,student;

    @BeforeEach void cleanThread() {
        assertFalse(TransactionSynchronizationManager.isActualTransactionActive());
        assertFalse(TransactionSynchronizationManager.hasResource(factory));
    }
    @BeforeAll void fixture() {
        cleanThread();
        new TransactionTemplate(transactions).executeWithoutResult(status->{
            var owner=User.create("PDF boundary teacher "+UUID.randomUUID(),Role.TEACHER);
            var denied=User.create("PDF boundary student "+UUID.randomUUID(),Role.STUDENT);
            em.persist(owner); em.persist(denied); em.flush();
            teacher=owner.getId(); student=denied.getId();
        });
    }
    boolean physical(EntityManager view) {
        // Observation only; the policy calls below, not this helper, execute the intended SQL.
        return view.unwrap(SessionImplementor.class).getJdbcCoordinator().getLogicalConnection().isPhysicallyConnected();
    }
    void noTransactionOrDataSourceBinding() {
        assertFalse(TransactionSynchronizationManager.isActualTransactionActive());
        assertFalse(TransactionSynchronizationManager.isSynchronizationActive());
        assertFalse(TransactionSynchronizationManager.hasResource(dataSource));
    }
    void withOsiv(java.util.function.Consumer<EntityManagerHolder> request) {
        EntityManager view=factory.createEntityManager();
        var holder=new EntityManagerHolder(view);
        TransactionSynchronizationManager.bindResource(factory,holder);
        try { request.accept(holder); }
        finally {
            try { assertSame(holder,TransactionSynchronizationManager.unbindResource(factory)); }
            finally { view.close(); } // This test owns this EntityManager, just as the OSIV request interceptor does.
        }
        noTransactionOrDataSourceBinding();
        assertFalse(TransactionSynchronizationManager.hasResource(factory));
    }

    @Test void directControllerStylePermissionQueryReallyRetainsPhysicalConnectionAndGuardRejectsIt() {
        withOsiv(holder->{
            assertFalse(physical(holder.getEntityManager()));
            policy.teacher(teacher);
            noTransactionOrDataSourceBinding();
            assertTrue(physical(holder.getEntityManager()),"Real OSIV retention must be reproduced, not mocked");
            assertEquals("INDEXING_TRANSACTION_BOUNDARY",assertThrows(IndexingFailure.class,()->hooks.boundary(0,false)).code());
            assertSame(holder,TransactionSynchronizationManager.getResource(factory));
            assertTrue(physical(holder.getEntityManager()),"Guard must not release or hide a request-owned connection");
        });
    }

    @Test void detachedConnectedHolderIsRestoredAndNeverMakesDirtyRequestPassTheGuard() {
        withOsiv(holder->{
            policy.teacher(teacher);
            assertTrue(physical(holder.getEntityManager()));
            store.teacher(teacher);
            assertSame(holder,TransactionSynchronizationManager.getResource(factory));
            assertTrue(physical(holder.getEntityManager()),"Unbinding is not connection release");
            assertEquals("INDEXING_TRANSACTION_BOUNDARY",assertThrows(IndexingFailure.class,()->hooks.boundary(0,false)).code());
        });
    }

    @Test void shortPermissionTransactionReturnsActualConnectionBeforeExternalBoundary() {
        withOsiv(holder->{
            store.teacher(teacher);
            assertSame(holder,TransactionSynchronizationManager.getResource(factory));
            noTransactionOrDataSourceBinding();
            assertFalse(physical(holder.getEntityManager()));
            assertDoesNotThrow(()->hooks.boundary(0,false));
        });
    }

    @Test void deniedRoleRestoresHolderAndSubsequentRequestOnSameThreadRemainsClean() {
        withOsiv(holder->{
            assertThrows(AuthorizationFailure.class,()->store.teacher(student));
            assertSame(holder,TransactionSynchronizationManager.getResource(factory));
            assertTrue(holder.getEntityManager().isOpen());
            noTransactionOrDataSourceBinding();
            assertFalse(physical(holder.getEntityManager()));
            assertDoesNotThrow(()->hooks.boundary(0,false));
            store.teacher(teacher);
            assertSame(holder,TransactionSynchronizationManager.getResource(factory));
            assertFalse(physical(holder.getEntityManager()));
        });
        // Same JUnit thread, new request holder after the denied request has ended.
        withOsiv(holder->{
            store.teacher(teacher);
            assertFalse(physical(holder.getEntityManager()));
            assertDoesNotThrow(()->hooks.boundary(0,false));
        });
    }

    @Test void realActiveTransactionStillFailsWithoutClosingOrSuspendingItsResources() {
        new TransactionTemplate(transactions).executeWithoutResult(status->{
            policy.teacher(teacher);
            Object holder=TransactionSynchronizationManager.getResource(factory);
            assertTrue(TransactionSynchronizationManager.isActualTransactionActive());
            assertTrue(TransactionSynchronizationManager.isSynchronizationActive());
            assertTrue(TransactionSynchronizationManager.hasResource(dataSource));
            assertTrue(physical(em));
            assertEquals("INDEXING_TRANSACTION_BOUNDARY",assertThrows(IndexingFailure.class,()->hooks.boundary(0,false)).code());
            assertSame(holder,TransactionSynchronizationManager.getResource(factory));
            assertTrue(TransactionSynchronizationManager.isActualTransactionActive());
            assertTrue(physical(em));
        });
        noTransactionOrDataSourceBinding();
        assertFalse(TransactionSynchronizationManager.hasResource(factory));
    }

    @Test void completedHttpResponsesReuseTheSameServerThreadWithoutTransactionOrIdentityState() throws Exception {
        final String filename="indexing-synthetic-44444444-4444-4444-8444-444444444444.pdf";
        var tx=new TransactionTemplate(transactions);
        long existing=tx.execute(status->em.createQuery(
            "select count(f) from UploadedFile f where f.originalFileName=:filename",Long.class)
            .setParameter("filename",filename).getSingleResult());
        assertEquals(0L,existing,"The unique synthetic HTTP case must not be replayed");
        String[] tokens=tx.execute(status->{
            // Select only the existing new-trial user, not any password credential fields.
            User owner=em.createQuery("select c.user from PasswordCredential c where c.email=:email",User.class)
                .setParameter("email","authz-owner@local.dodream.invalid").getSingleResult();
            assertEquals(Role.TEACHER,owner.getRole());
            return new String[]{jwt.createAccessToken(em.find(User.class,student)),jwt.createAccessToken(owner)};
        });
        assertTrue(completedRequests.events.isEmpty());
        byte[] pdf="%PDF-1.4\n% DO-DREAM LOCAL SYNTHETIC FIXTURE\n%%EOF\n".getBytes(StandardCharsets.US_ASCII);
        var client=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3))
            .followRedirects(HttpClient.Redirect.NEVER).version(HttpClient.Version.HTTP_1_1)
            .proxy(new java.net.ProxySelector() {
                @Override public List<java.net.Proxy> select(URI uri) { return List.of(java.net.Proxy.NO_PROXY); }
                @Override public void connectFailed(URI uri,java.net.SocketAddress address,IOException failure) { }
            }).build();
        var completions=new ArrayList<RequestCompletion>();
        long acceptedFile=0;
        for(int index=0;index<3;index++) {
            byte[] input=index==1?"not a PDF".getBytes(StandardCharsets.US_ASCII):pdf;
            var request=HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+"/api/pdf/upload-and-parse?filename="+filename))
                .timeout(Duration.ofSeconds(25)).header("Content-Type","application/pdf")
                .header("Authorization","Bearer "+tokens[index==0?0:1])
                .POST(HttpRequest.BodyPublishers.ofByteArray(input)).build();
            var response=client.send(request,HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            RequestCompletion completed=completedRequests.events.poll(5,TimeUnit.SECONDS);
            assertNotNull(completed,"Server filter must finish before the next HTTP request");
            int expected=index==0?403:index==1?400:200;
            assertEquals(expected,response.statusCode());
            assertEquals(expected,completed.status());
            assertFalse(completed.transactionActive());
            assertFalse(completed.synchronizationActive());
            assertFalse(completed.entityManagerBound());
            assertFalse(completed.dataSourceBound());
            assertFalse(completed.asyncStarted());
            assertTrue(completed.securityContextCleared());
            completions.add(completed);
            if(index==2) acceptedFile=IndexingSource.JSON.readTree(response.body()).path("pdfId").asLong();
        }
        assertEquals(1L,completions.stream().map(RequestCompletion::threadId).distinct().count(),
            "The actual completed responses must reuse one Tomcat thread");
        assertNotEquals(Thread.currentThread().getId(),completions.get(0).threadId(),"Actual server HTTP dispatch is required");
        assertTrue(completedRequests.events.isEmpty());
        assertTrue(acceptedFile>0);
        long pdfId=acceptedFile;
        tx.executeWithoutResult(status->{
            assertEquals(1L,em.createQuery("select count(f) from UploadedFile f where f.id=:id and f.originalFileName=:filename",Long.class)
                .setParameter("id",pdfId).setParameter("filename",filename).getSingleResult());
            Number jobs=(Number)em.createNativeQuery("SELECT COUNT(*) FROM index_jobs j JOIN index_resources r ON r.id=j.resource_pk WHERE r.resource_kind='PDF' AND r.resource_id=:id")
                .setParameter("id",pdfId).getSingleResult();
            assertEquals(1L,jobs.longValue());
        });
        // Keep the accepted synthetic file, objects and job as evidence. No cleanup SQL or retry.
    }

    record RequestCompletion(long threadId,int status,boolean transactionActive,boolean synchronizationActive,
        boolean entityManagerBound,boolean dataSourceBound,boolean securityContextCleared,boolean asyncStarted) {}
    static final class CompletedRequests {
        final ArrayBlockingQueue<RequestCompletion> events=new ArrayBlockingQueue<>(4);
    }
    @TestConfiguration(proxyBeanMethods=false)
    static class HttpObservationConfiguration {
        @Bean CompletedRequests completedRequests() { return new CompletedRequests(); }
        @Bean FilterRegistrationBean<OncePerRequestFilter> completedPdfRequestObserver(
            EntityManagerFactory factory,DataSource dataSource,CompletedRequests completed) {
            // Read the locked Spring Security strategy's existing ThreadLocal without creating a new context.
            Object contextHolder=ReflectionTestUtils.getField(SecurityContextHolder.getContextHolderStrategy(),"contextHolder");
            if(!(contextHolder instanceof ThreadLocal<?> securityHolder))
                throw new IllegalStateException("A directly observable thread-local security strategy is required");
            var filter=new OncePerRequestFilter() {
                @Override protected boolean shouldNotFilter(HttpServletRequest request) {
                    return !"POST".equals(request.getMethod()) || !"/api/pdf/upload-and-parse".equals(request.getRequestURI());
                }
                @Override protected void doFilterInternal(HttpServletRequest request,HttpServletResponse response,FilterChain chain)
                    throws ServletException,IOException {
                    try { chain.doFilter(request,response); }
                    finally {
                        completed.events.add(new RequestCompletion(Thread.currentThread().getId(),response.getStatus(),
                            TransactionSynchronizationManager.isActualTransactionActive(),
                            TransactionSynchronizationManager.isSynchronizationActive(),
                            TransactionSynchronizationManager.hasResource(factory),
                            TransactionSynchronizationManager.hasResource(dataSource),
                            securityHolder.get()==null,request.isAsyncStarted()));
                    }
                }
            };
            FilterRegistrationBean<OncePerRequestFilter> registration=new FilterRegistrationBean<>(filter);
            registration.setOrder(Ordered.HIGHEST_PRECEDENCE);
            return registration;
        }
    }
}
