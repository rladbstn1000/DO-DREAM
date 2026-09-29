package A704.DODREAM.auth.service;

import java.time.Instant;
import A704.DODREAM.auth.exception.AuthException;
import A704.DODREAM.auth.util.JwtUtil;
import A704.DODREAM.user.entity.Role;
import A704.DODREAM.user.entity.User;
import A704.DODREAM.user.repository.UserRepository;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class AuthSessionService {
    private final JwtUtil jwt;
    private final RefreshTokenService sessions;
    private final UserRepository users;
    public record Tokens(String accessToken, String refreshToken, Instant refreshExpiresAt) {}

    public Tokens login(User user) {
        Tokens tokens = issue(user);
        sessions.save(user.getId(), tokens.refreshToken(), tokens.refreshExpiresAt());
        return tokens;
    }

    public Tokens refresh(String refreshToken, Role role) {
        Claims claims = refreshClaims(refreshToken, role);
        User user = users.findById(Long.parseLong(claims.getSubject())).orElseThrow(AuthException::unauthorized);
        if (user.getRole() != role) throw AuthException.unauthorized();
        Tokens tokens = issue(user);
        if (!sessions.validateAndRotate(user.getId(), refreshToken, tokens.refreshToken(), tokens.refreshExpiresAt())) {
            throw AuthException.unauthorized();
        }
        return tokens;
    }

    public void logout(String refreshToken, Role role) {
        Claims claims = refreshClaims(refreshToken, role);
        sessions.revoke(Long.parseLong(claims.getSubject()));
    }

    private Claims refreshClaims(String token, Role role) {
        try {
            Claims claims = jwt.parseRefresh(token).getPayload();
            if (!role.name().equals(claims.get("role", String.class))) throw AuthException.unauthorized();
            return claims;
        } catch (JwtException exception) { throw AuthException.unauthorized(); }
    }

    private Tokens issue(User user) {
        String refresh = jwt.createRefreshToken(user);
        return new Tokens(jwt.createAccessToken(user), refresh, jwt.parseRefresh(refresh).getPayload().getExpiration().toInstant());
    }
}
