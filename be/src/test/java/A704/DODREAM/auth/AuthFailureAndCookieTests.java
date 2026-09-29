package A704.DODREAM.auth;

import java.time.Instant;
import java.util.List;
import A704.DODREAM.auth.exception.AuthException;
import A704.DODREAM.auth.service.RefreshTokenService;
import A704.DODREAM.auth.util.CookieUtil;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.http.HttpStatus;
import org.springframework.mock.env.MockEnvironment;
import org.springframework.mock.web.MockHttpServletResponse;
import static org.junit.jupiter.api.Assertions.*;

class AuthFailureAndCookieTests {
    @Test
    void everyRedisOperationFailsAs503WithoutRawErrors() {
        var unavailable = new StringRedisTemplate() {
            @Override public <T> T execute(RedisScript<T> script, List<String> keys, Object... args) {
                throw new DataAccessResourceFailureException("test transport failure");
            }
            @Override public Boolean delete(String key) { throw new DataAccessResourceFailureException("test transport failure"); }
        };
        var sessions = new RefreshTokenService(unavailable);
        Instant expiry = Instant.now().plusSeconds(30);
        assertEquals(HttpStatus.SERVICE_UNAVAILABLE, assertThrows(AuthException.class,
            () -> sessions.save(1, "synthetic-test-input", expiry)).status());
        assertEquals(HttpStatus.SERVICE_UNAVAILABLE, assertThrows(AuthException.class,
            () -> sessions.validateAndRotate(1, "synthetic-test-input", "replacement", expiry)).status());
        assertEquals(HttpStatus.SERVICE_UNAVAILABLE, assertThrows(AuthException.class,
            () -> sessions.revoke(1)).status());
    }
    @Test
    void localCookieIssueAndDeletionUseTheSameScope() {
        MockEnvironment local = new MockEnvironment(); local.setActiveProfiles("local");
        CookieUtil cookies = new CookieUtil(false, local);
        MockHttpServletResponse issued = new MockHttpServletResponse(), deleted = new MockHttpServletResponse();
        cookies.addRefreshCookie(issued, "synthetic-test-input", Instant.now().plusSeconds(100));
        cookies.deleteRefreshCookie(deleted);
        for (var response : List.of(issued, deleted)) {
            String header = response.getHeader("Set-Cookie");
            assertTrue(header.contains("Path=/api/auth")); assertTrue(header.contains("HttpOnly"));
            assertTrue(header.contains("SameSite=Lax")); assertFalse(header.contains("Secure"));
        }
        assertTrue(deleted.getHeader("Set-Cookie").contains("Max-Age=0"));
        assertThrows(IllegalArgumentException.class, () -> new CookieUtil(false, new MockEnvironment()));
        MockHttpServletResponse production = new MockHttpServletResponse();
        new CookieUtil(true, new MockEnvironment()).addRefreshCookie(production, "synthetic-test-input", Instant.now().plusSeconds(100));
        assertTrue(production.getHeader("Set-Cookie").contains("Secure"));
    }
}
