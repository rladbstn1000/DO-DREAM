package A704.DODREAM.auth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import A704.DODREAM.auth.service.RefreshTokenService;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.ActiveProfiles;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@ActiveProfiles("local")
class RefreshTokenRedisTests {
    @Value("${spring.data.redis.host}") private String host;
    @Value("${spring.data.redis.port}") private int port;
    private LettuceConnectionFactory firstFactory, secondFactory;
    private StringRedisTemplate first, second;
    private RefreshTokenService serviceA, serviceB;
    private long userId;
    private String key;
    @BeforeEach
    void connectIndependentClients() {
        firstFactory = factory(); secondFactory = factory();
        first = new StringRedisTemplate(firstFactory); second = new StringRedisTemplate(secondFactory);
        serviceA = new RefreshTokenService(first); serviceB = new RefreshTokenService(second);
        userId = 8000000000000000000L + ThreadLocalRandom.current().nextLong(100000000000000000L);
        key = "refresh:v2:" + userId;
    }
    private LettuceConnectionFactory factory() {
        var factory = new LettuceConnectionFactory(host, port); factory.afterPropertiesSet(); factory.start(); return factory;
    }
    @AfterEach
    void removeOnlyThisTestKey() {
        if (first != null) first.delete(key);
        if (firstFactory != null) firstFactory.destroy();
        if (secondFactory != null) secondFactory.destroy();
    }
    private String randomToken() { return UUID.randomUUID().toString(); }
    @Test
    void sequentialRotationHashAndAbsoluteExpiry() throws Exception {
        String old = randomToken(), replacement = randomToken(); Instant expiry = Instant.now().plusSeconds(60);
        serviceA.save(userId, old, expiry);
        String stored = first.opsForValue().get(key);
        assertTrue(stored != null && stored.matches("[a-f0-9]{64}")); assertFalse(old.equals(stored));
        assertTrue(serviceB.validateAndRotate(userId, old, replacement, expiry));
        assertFalse(serviceA.validateAndRotate(userId, old, randomToken(), expiry));
        assertTrue(serviceA.validateAndRotate(userId, replacement, randomToken(), expiry));
        Long ttl = first.getExpire(key, TimeUnit.MILLISECONDS);
        assertTrue(ttl != null && ttl > 55000 && ttl <= 60000);
        serviceA.revoke(userId);
        assertFalse(serviceB.validateAndRotate(userId, replacement, randomToken(), expiry));
        serviceA.save(userId, old, Instant.now().plusMillis(150));
        Thread.sleep(250);
        assertFalse(serviceB.validateAndRotate(userId, old, randomToken(), expiry));
    }
    @Test
    void twelveConcurrentIndependentClientsHaveExactlyOneWinnerAcrossThreeRounds() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(12);
        try {
            for (int round = 0; round < 3; round++) {
                String old = randomToken(); Instant expiry = Instant.now().plusSeconds(60);
                serviceA.save(userId, old, expiry);
                CyclicBarrier barrier = new CyclicBarrier(12);
                List<Future<String>> futures = new ArrayList<>();
                for (int i = 0; i < 12; i++) {
                    var service = i % 2 == 0 ? serviceA : serviceB;
                    String replacement = randomToken();
                    futures.add(pool.submit(() -> {
                        barrier.await(5, TimeUnit.SECONDS);
                        return service.validateAndRotate(userId, old, replacement, expiry) ? replacement : null;
                    }));
                }
                List<String> winners = new ArrayList<>();
                for (var future : futures) { String winner = future.get(10, TimeUnit.SECONDS); if (winner != null) winners.add(winner); }
                assertEquals(1, winners.size());
                String hash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(winners.get(0).getBytes(StandardCharsets.UTF_8)));
                assertTrue(hash.equals(first.opsForValue().get(key)));
                assertTrue(serviceB.validateAndRotate(userId, winners.get(0), randomToken(), expiry));
            }
        } finally { pool.shutdownNow(); }
    }
    @Test
    void logoutAndRotationRaceCannotRestoreDeletedSession() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            for (int round = 0; round < 3; round++) {
                String old = randomToken(), replacement = randomToken(); Instant expiry = Instant.now().plusSeconds(60);
                serviceA.save(userId, old, expiry); CyclicBarrier barrier = new CyclicBarrier(2);
                Future<?> refresh = pool.submit(() -> { barrier.await(); return serviceA.validateAndRotate(userId, old, replacement, expiry); });
                Future<?> logout = pool.submit(() -> { barrier.await(); serviceB.revoke(userId); return null; });
                refresh.get(10, TimeUnit.SECONDS); logout.get(10, TimeUnit.SECONDS);
                assertFalse(Boolean.TRUE.equals(first.hasKey(key)));
                assertFalse(serviceA.validateAndRotate(userId, old, randomToken(), expiry));
                assertFalse(serviceB.validateAndRotate(userId, replacement, randomToken(), expiry));
            }
        } finally { pool.shutdownNow(); }
    }
}
