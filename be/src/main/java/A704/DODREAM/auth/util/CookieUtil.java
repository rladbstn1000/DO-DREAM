package A704.DODREAM.auth.util;

import java.time.Duration;
import java.time.Instant;
import A704.DODREAM.auth.exception.AuthException;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.stereotype.Component;

@Component
public class CookieUtil {
    public static final String REFRESH_COOKIE = "refresh";
    private final boolean secure;
    public CookieUtil(@Value("${auth.cookie.secure:true}") boolean secure, Environment environment) {
        if (!secure && !environment.acceptsProfiles(Profiles.of("local", "test"))) {
            throw new IllegalArgumentException("Insecure auth cookies are only permitted for local/test HTTP");
        }
        this.secure = secure;
    }
    public boolean secure() { return secure; }
    private ResponseCookie.ResponseCookieBuilder cookie(String value) {
        return ResponseCookie.from(REFRESH_COOKIE, value).httpOnly(true).secure(secure).path("/api/auth").sameSite("Lax");
    }
    public void addRefreshCookie(HttpServletResponse response, String token, Instant expiresAt) {
        long seconds = Math.max(0, expiresAt.getEpochSecond() - Instant.now().getEpochSecond());
        response.addHeader(HttpHeaders.SET_COOKIE, cookie(token).maxAge(Duration.ofSeconds(seconds)).build().toString());
    }
    public void deleteRefreshCookie(HttpServletResponse response) {
        response.addHeader(HttpHeaders.SET_COOKIE, cookie("").maxAge(Duration.ZERO).build().toString());
    }
    public String refreshFrom(HttpServletRequest request) {
        String found = null;
        if (request.getCookies() != null) for (Cookie cookie : request.getCookies()) {
            if (REFRESH_COOKIE.equals(cookie.getName())) {
                if (found != null) throw AuthException.unauthorized();
                found = cookie.getValue();
            }
        }
        if (found == null || found.isBlank()) throw AuthException.unauthorized();
        return found;
    }
}
