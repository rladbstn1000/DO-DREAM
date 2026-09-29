package A704.DODREAM.auth.util;

import java.time.Instant;
import java.util.Base64;
import java.util.Date;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import javax.crypto.SecretKey;

import A704.DODREAM.user.entity.User;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jws;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.JwtParser;
import io.jsonwebtoken.Jwts;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.stereotype.Component;

/** Shared Spring/FastAPI contract. Legacy tokens deliberately require a fresh login. */
@Component
public class JwtUtil {
    public static final long CLOCK_SKEW_SECONDS = 5;
    private static final long MAX_NUMERIC_DATE = 253402300799L;
    private final SecretKey key;
    private final JwtParser parser;
    private final long accessExpSeconds;
    private final long refreshExpSeconds;
    private final String issuer;
    private final String audience;
    private final ObjectMapper json = new ObjectMapper().enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);

    public JwtUtil(@Value("${jwt.secret}") String secretBase64,
                   @Value("${jwt.access-exp-seconds:900}") long accessExpSeconds,
                   @Value("${jwt.refresh-exp-seconds:1209600}") long refreshExpSeconds,
                   @Value("${jwt.issuer:dodream}") String issuer,
                   @Value("${jwt.audience:dodream-api}") String audience,
                   Environment environment) {
        try {
            byte[] decoded = Base64.getDecoder().decode(secretBase64);
            if (decoded.length < 32 || !Base64.getEncoder().encodeToString(decoded).equals(secretBase64)) {
                throw new IllegalArgumentException();
            }
            key = new SecretKeySpec(decoded, "HmacSHA256");
        } catch (Exception ignored) {
            throw new IllegalArgumentException("JWT signing key must be canonical Base64 encoding of at least 32 bytes");
        }
        if (!"dodream".equals(issuer) || !"dodream-api".equals(audience)) {
            throw new IllegalArgumentException("JWT issuer/audience must match the shared authentication contract");
        }
        if (accessExpSeconds < 1 || accessExpSeconds > 900 || refreshExpSeconds != 1209600
            || (accessExpSeconds != 900 && !environment.acceptsProfiles(Profiles.of("local", "test")))) {
            throw new IllegalArgumentException("JWT lifetime must be AT 900 / RT 1209600; shorter AT is local/test only");
        }
        this.accessExpSeconds = accessExpSeconds;
        this.refreshExpSeconds = refreshExpSeconds;
        this.issuer = issuer;
        this.audience = audience;
        var builder = Jwts.parser().verifyWith(key).requireIssuer(issuer).requireAudience(audience)
            .clockSkewSeconds(CLOCK_SKEW_SECONDS);
        var algorithms = builder.sig();
        // JJWT 0.12.5 disallows an empty registry, so retain HS256 while removing the others.
        for (var algorithm : Jwts.SIG.get().values()) {
            if (!"HS256".equals(algorithm.getId())) algorithms.remove(algorithm);
        }
        parser = algorithms.and().build();
    }

    public String createAccessToken(User user) { return create(user, "access", accessExpSeconds); }
    public String createRefreshToken(User user) { return create(user, "refresh", refreshExpSeconds); }

    private String create(User user, String use, long seconds) {
        Instant now = Instant.ofEpochSecond(Instant.now().getEpochSecond());
        return Jwts.builder().subject(String.valueOf(user.getId())).issuer(issuer)
            .audience().add(audience).and().id(UUID.randomUUID().toString())
            .claim("token_use", use).claim("role", user.getRole().name()).claim("name", user.getName())
            .issuedAt(Date.from(now)).notBefore(Date.from(now)).expiration(Date.from(now.plusSeconds(seconds)))
            .signWith(key, Jwts.SIG.HS256).compact();
    }

    public Jws<Claims> parseAccess(String token) { return parse(token, "access", 900); }
    public Jws<Claims> parseRefresh(String token) { return parse(token, "refresh", 1209600); }

    private Jws<Claims> parse(String token, String use, long maxLifetime) {
        try {
            if (token == null || token.length() > 8192 || !token.matches("[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+")) {
                throw new IllegalArgumentException();
            }
            Jws<Claims> signed = parser.parseSignedClaims(token);
            String[] segments = token.split("\\.");
            Map<String, Object> header = json.readValue(Base64.getUrlDecoder().decode(segments[0]), new TypeReference<>() {});
            Map<String, Object> claims = json.readValue(Base64.getUrlDecoder().decode(segments[1]), new TypeReference<>() {});
            if (!"HS256".equals(header.get("alg")) || !issuer.equals(claims.get("iss"))
                || !use.equals(claims.get("token_use"))) throw new IllegalArgumentException();
            Object aud = claims.get("aud");
            if (!(audience.equals(aud) || List.of(audience).equals(aud))) throw new IllegalArgumentException();
            Object subject = claims.get("sub");
            if (!(subject instanceof String sub) || !sub.matches("[1-9][0-9]*") || Long.parseLong(sub) <= 0) {
                throw new IllegalArgumentException();
            }
            if (!(claims.get("jti") instanceof String id)
                || !UUID.fromString(id).toString().equals(id)) throw new IllegalArgumentException();
            if (!(claims.get("role") instanceof String role) || !(role.equals("TEACHER") || role.equals("STUDENT"))) {
                throw new IllegalArgumentException();
            }
            if (claims.containsKey("name") && (!(claims.get("name") instanceof String name) || name.codePoints().allMatch(c -> Character.isWhitespace(c) || Character.isSpaceChar(c) || c == 0x85))) {
                throw new IllegalArgumentException();
            }
            long issued = numericDate(claims.get("iat"));
            long before = numericDate(claims.get("nbf"));
            long expires = numericDate(claims.get("exp"));
            long now = Instant.now().getEpochSecond();
            if (issued > before || before >= expires || expires - issued > maxLifetime
                || issued > now + CLOCK_SKEW_SECONDS || before > now + CLOCK_SKEW_SECONDS
                || expires <= now - CLOCK_SKEW_SECONDS) throw new IllegalArgumentException();
            return signed;
        } catch (Exception ignored) {
            // Never propagate parser messages that may contain a submitted claim or token.
            throw new JwtException("Invalid authentication token");
        }
    }

    private long numericDate(Object value) {
        if (!(value instanceof Integer || value instanceof Long)) throw new IllegalArgumentException();
        long result = ((Number) value).longValue();
        if (result <= 0 || result > MAX_NUMERIC_DATE) throw new IllegalArgumentException();
        return result;
    }
}
