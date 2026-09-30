package A704.DODREAM.auth;

import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.*;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import A704.DODREAM.auth.util.JwtUtil;
import A704.DODREAM.user.entity.Role;
import A704.DODREAM.user.entity.User;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.jsonwebtoken.JwtException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.mock.env.MockEnvironment;
import org.springframework.test.util.ReflectionTestUtils;
import static org.junit.jupiter.api.Assertions.*;

class JwtContractTests {
    private final ObjectMapper json = new ObjectMapper();
    private byte[] secret;
    private String encodedSecret;
    private JwtUtil jwt;
    private User user;
    @BeforeEach
    void setup() {
        secret = new byte[64]; new SecureRandom().nextBytes(secret);
        encodedSecret = Base64.getEncoder().encodeToString(secret);
        jwt = build(encodedSecret, 900, new MockEnvironment());
        user = User.create("Synthetic account", Role.TEACHER);
        ReflectionTestUtils.setField(user, "id", 1L);
    }
    private JwtUtil build(String key, long seconds, MockEnvironment environment) {
        return new JwtUtil(key, seconds, 1209600, "dodream", "dodream-api", environment);
    }
    private Map<String, Object> claims() {
        long now = Instant.now().getEpochSecond();
        Map<String, Object> claims = new LinkedHashMap<>();
        claims.put("iss", "dodream"); claims.put("aud", List.of("dodream-api"));
        claims.put("sub", "1"); claims.put("jti", UUID.randomUUID().toString());
        claims.put("role", "TEACHER"); claims.put("token_use", "access");
        claims.put("iat", now); claims.put("nbf", now); claims.put("exp", now + 900);
        return claims;
    }
    private String sign(Map<String, Object> claims) throws Exception { return signRaw(json.writeValueAsString(claims), "HS256"); }
    private String signRaw(String payload, String algorithm) throws Exception {
        Base64.Encoder encoder = Base64.getUrlEncoder().withoutPadding();
        String input = encoder.encodeToString(("{\"alg\":\"" + algorithm + "\"}").getBytes(StandardCharsets.UTF_8))
            + "." + encoder.encodeToString(payload.getBytes(StandardCharsets.UTF_8));
        Mac mac = Mac.getInstance(algorithm.equals("HS384") ? "HmacSHA384" : "HmacSHA256");
        mac.init(new SecretKeySpec(secret, mac.getAlgorithm()));
        return input + "." + encoder.encodeToString(mac.doFinal(input.getBytes(StandardCharsets.UTF_8)));
    }
    private void rejects(Map<String, Object> claims) throws Exception {
        String token = sign(claims);
        assertThrows(JwtException.class, () -> jwt.parseAccess(token));
    }
    @Test
    void issueSeparatesKindsLifetimeAndEveryJti() {
        String access = jwt.createAccessToken(user), refresh = jwt.createRefreshToken(user);
        var at = jwt.parseAccess(access).getPayload(); var rt = jwt.parseRefresh(refresh).getPayload();
        assertEquals(900000, at.getExpiration().getTime() - at.getIssuedAt().getTime());
        assertEquals(1209600000, rt.getExpiration().getTime() - rt.getIssuedAt().getTime());
        assertThrows(JwtException.class, () -> jwt.parseAccess(refresh));
        assertThrows(JwtException.class, () -> jwt.parseRefresh(access));
        Set<String> ids = new HashSet<>();
        for (int i = 0; i < 20; i++) ids.add(jwt.parseRefresh(jwt.createRefreshToken(user)).getPayload().getId());
        assertEquals(20, ids.size());
    }
    @ParameterizedTest
    @ValueSource(strings = {"iss", "aud", "sub", "jti", "role", "token_use", "iat", "nbf", "exp"})
    void everyMandatoryClaimIsRequired(String key) throws Exception {
        var claims = claims(); claims.remove(key); rejects(claims);
    }
    @ParameterizedTest
    @ValueSource(strings = {"wrong-issuer", "wrong-audience", "extra-audience", "numeric-sub", "zero-sub", "leading-zero-sub", "overflow-sub", "role", "use", "jti", "null-name", "blank-name", "nbsp-name", "nel-name", "numeric-name", "expired", "future", "long-life", "bad-order", "float-date", "string-date", "boolean-date"})
    void malformedClaimValuesAreRejected(String condition) throws Exception {
        var c = claims(); long now = Instant.now().getEpochSecond();
        switch (condition) {
            case "wrong-issuer" -> c.put("iss", "other");
            case "wrong-audience" -> c.put("aud", "other");
            case "extra-audience" -> c.put("aud", List.of("dodream-api", "other"));
            case "numeric-sub" -> c.put("sub", 1);
            case "zero-sub" -> c.put("sub", "0");
            case "leading-zero-sub" -> c.put("sub", "01");
            case "overflow-sub" -> c.put("sub", "9223372036854775808");
            case "role" -> c.put("role", "teacher");
            case "use" -> c.put("token_use", "refresh");
            case "jti" -> c.put("jti", "not-a-uuid");
            case "null-name" -> c.put("name", null);
            case "blank-name" -> c.put("name", " ");
            case "nbsp-name" -> c.put("name", "\u00a0");
            case "nel-name" -> c.put("name", "\u0085");
            case "numeric-name" -> c.put("name", 2);
            case "expired" -> { c.put("iat", now-1000); c.put("nbf", now-1000); c.put("exp", now-100); }
            case "future" -> { c.put("iat", now+60); c.put("nbf", now+60); c.put("exp", now+120); }
            case "long-life" -> c.put("exp", now+901);
            case "bad-order" -> c.put("nbf", now-1);
            case "float-date" -> c.put("exp", (double) (now+100));
            case "string-date" -> c.put("exp", Long.toString(now+100));
            case "boolean-date" -> c.put("iat", true);
        }
        rejects(c);
    }
    @Test
    void algorithmSignatureDuplicateKeysAndOversizeAreRejected() throws Exception {
        String wrongAlgorithm = signRaw(json.writeValueAsString(claims()), "HS384");
        assertThrows(JwtException.class, () -> jwt.parseAccess(wrongAlgorithm));
        String token = sign(claims());
        int index = token.lastIndexOf('.') + 1;
        String damaged = token.substring(0, index) + (token.charAt(index) == 'A' ? 'B' : 'A') + token.substring(index+1);
        assertThrows(JwtException.class, () -> jwt.parseAccess(damaged));
        String duplicate = signRaw(json.writeValueAsString(claims()).replace("{", "{\"sub\":\"2\","), "HS256");
        assertThrows(JwtException.class, () -> jwt.parseAccess(duplicate));
        assertThrows(JwtException.class, () -> jwt.parseAccess("a".repeat(8193)));
        var largeClaims = claims();
        largeClaims.put("name", "x".repeat(9000));
        String signedOversize = sign(largeClaims);
        assertTrue(signedOversize.length() > 8192);
        assertThrows(JwtException.class, () -> jwt.parseAccess(signedOversize));
    }
    @Test
    void validSingletonAudienceAndOptionalNameAreAccepted() throws Exception {
        var c = claims(); c.put("aud", "dodream-api");
        assertEquals("1", jwt.parseAccess(sign(c)).getPayload().getSubject());
    }
    @Test
    void configurationFailsClosedAndShortLifetimeIsLocalOnly() {
        for (String invalid : List.of("", "not-base64", Base64.getEncoder().encodeToString(new byte[16]))) {
            assertThrows(IllegalArgumentException.class, () -> build(invalid, 900, new MockEnvironment()));
        }
        assertThrows(IllegalArgumentException.class, () -> build(encodedSecret, 901, new MockEnvironment()));
        assertThrows(IllegalArgumentException.class, () -> build(encodedSecret, 2, new MockEnvironment()));
        MockEnvironment local = new MockEnvironment(); local.setActiveProfiles("local");
        JwtUtil shortLived = build(encodedSecret, 2, local);
        var token = shortLived.parseAccess(shortLived.createAccessToken(user)).getPayload();
        assertEquals(2000, token.getExpiration().getTime() - token.getIssuedAt().getTime());
    }
}
