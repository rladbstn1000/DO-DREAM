package A704.DODREAM.auth.service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.HexFormat;
import java.util.List;
import A704.DODREAM.auth.exception.AuthException;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;
import lombok.RequiredArgsConstructor;

/** One current session per user, versioned SHA-256 storage. Legacy keys expire untouched. */
@Service
@RequiredArgsConstructor
public class RefreshTokenService {
    private final StringRedisTemplate redis;
    private static final DefaultRedisScript<Long> SAVE = new DefaultRedisScript<>("""
        local now = redis.call('TIME')
        if tonumber(ARGV[2]) <= tonumber(now[1]) * 1000 + math.floor(tonumber(now[2]) / 1000) then return 0 end
        redis.call('SET', KEYS[1], ARGV[1], 'PXAT', ARGV[2])
        return 1
        """, Long.class);
    private static final DefaultRedisScript<Long> ROTATE = new DefaultRedisScript<>("""
        local current = redis.call('GET', KEYS[1])
        if not current or current ~= ARGV[1] then return 0 end
        local now = redis.call('TIME')
        if tonumber(ARGV[3]) <= tonumber(now[1]) * 1000 + math.floor(tonumber(now[2]) / 1000) then return 0 end
        redis.call('SET', KEYS[1], ARGV[2], 'PXAT', ARGV[3])
        return 1
        """, Long.class);

    private String key(long userId) { return "refresh:v2:" + userId; }

    public void save(long userId, String token, Instant expiresAt) {
        try {
            Long saved = redis.execute(SAVE, List.of(key(userId)), hash(token), Long.toString(expiresAt.toEpochMilli()));
            if (!Long.valueOf(1).equals(saved)) throw AuthException.unauthorized();
        } catch (DataAccessException exception) { throw AuthException.unavailable(); }
    }

    public boolean validateAndRotate(long userId, String presented, String replacement, Instant expiresAt) {
        try {
            return Long.valueOf(1).equals(redis.execute(ROTATE, List.of(key(userId)), hash(presented),
                hash(replacement), Long.toString(expiresAt.toEpochMilli())));
        } catch (DataAccessException exception) { throw AuthException.unavailable(); }
    }

    /** A verified refresh token revokes the user's current session, including a concurrently rotated one. */
    public void revoke(long userId) {
        try { redis.delete(key(userId)); }
        catch (DataAccessException exception) { throw AuthException.unavailable(); }
    }

    private String hash(String token) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(token.getBytes(StandardCharsets.UTF_8)));
        } catch (java.security.NoSuchAlgorithmException exception) {
            throw new IllegalStateException("Required SHA-256 implementation unavailable");
        }
    }
}
