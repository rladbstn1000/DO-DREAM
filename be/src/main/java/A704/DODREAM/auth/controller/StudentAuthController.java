package A704.DODREAM.auth.controller;

import A704.DODREAM.auth.dto.request.StudentLoginRequest;
import A704.DODREAM.auth.dto.request.StudentSignupRequest;
import A704.DODREAM.auth.dto.request.StudentVerifyRequest;
import A704.DODREAM.auth.dto.response.TokenResponse;
import A704.DODREAM.auth.exception.AuthException;
import A704.DODREAM.auth.service.AuthSessionService;
import A704.DODREAM.auth.service.StudentAuthService;
import A704.DODREAM.auth.util.CookieUtil;
import A704.DODREAM.user.entity.Role;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@io.swagger.v3.oas.annotations.tags.Tag(name = "Student Auth API", description = "학생 인증 API")
@RestController
@RequestMapping("/api/auth/student")
@RequiredArgsConstructor
public class StudentAuthController {
    private final StudentAuthService studentAuthService;
    private final AuthSessionService sessions;
    private final CookieUtil cookies;
    public record NativeTokens(String accessToken, String refreshToken) {}
    public record RefreshRequest(String refreshToken) {}

    @io.swagger.v3.oas.annotations.Operation(summary = "사전 인증")
    @PostMapping("/verify")
    public ResponseEntity<Void> verify(@RequestBody StudentVerifyRequest request) {
        studentAuthService.verify(request);
        return ResponseEntity.ok().build();
    }
    @io.swagger.v3.oas.annotations.Operation(summary = "회원가입")
    @PostMapping("/register")
    public ResponseEntity<Void> register(@RequestBody StudentSignupRequest request) {
        studentAuthService.signup(request);
        return ResponseEntity.ok().build();
    }
    @io.swagger.v3.oas.annotations.Operation(summary = "로그인: Access Token 응답 / Refresh Token HttpOnly 쿠키")
    @PostMapping("/login")
    public ResponseEntity<TokenResponse> login(@RequestBody StudentLoginRequest request, HttpServletResponse response) {
        return cookieResponse(sessions.login(studentAuthService.authenticate(request)), response);
    }
    @io.swagger.v3.oas.annotations.Operation(summary = "쿠키 Refresh Token 원자 회전")
    @PostMapping("/refresh")
    public ResponseEntity<TokenResponse> refresh(HttpServletRequest request, HttpServletResponse response) {
        return cookieResponse(sessions.refresh(cookies.refreshFrom(request), Role.STUDENT), response);
    }
    @io.swagger.v3.oas.annotations.Operation(summary = "현재 사용자 Refresh 세션 폐기")
    @PostMapping("/logout")
    public ResponseEntity<Void> logout(HttpServletRequest request, HttpServletResponse response) {
        sessions.logout(cookies.refreshFrom(request), Role.STUDENT);
        cookies.deleteRefreshCookie(response);
        return ResponseEntity.ok().build();
    }

    // Explicit token transport: no ambient cookie authentication, no Set-Cookie, no platform-header bypass.
    @io.swagger.v3.oas.annotations.Operation(summary = "네이티브 로그인: 명시적 토큰 응답")
    @PostMapping("/native/login")
    public ResponseEntity<NativeTokens> nativeLogin(@RequestBody StudentLoginRequest body, HttpServletRequest request) {
        rejectCookies(request);
        return nativeResponse(sessions.login(studentAuthService.authenticate(body)));
    }
    @io.swagger.v3.oas.annotations.Operation(summary = "네이티브 Refresh Token 원자 회전")
    @PostMapping("/native/refresh")
    public ResponseEntity<NativeTokens> nativeRefresh(@RequestBody RefreshRequest body, HttpServletRequest request) {
        rejectCookies(request);
        return nativeResponse(sessions.refresh(body.refreshToken(), Role.STUDENT));
    }
    @io.swagger.v3.oas.annotations.Operation(summary = "네이티브 현재 사용자 Refresh 세션 폐기")
    @PostMapping("/native/logout")
    public ResponseEntity<Void> nativeLogout(@RequestBody RefreshRequest body, HttpServletRequest request) {
        rejectCookies(request);
        sessions.logout(body.refreshToken(), Role.STUDENT);
        return ResponseEntity.ok().build();
    }
    private void rejectCookies(HttpServletRequest request) {
        if (request.getHeader("Cookie") != null) {
            throw new AuthException(HttpStatus.BAD_REQUEST, "NATIVE_COOKIE_NOT_ALLOWED", "Native authentication requires explicit token transport without cookies");
        }
    }
    private ResponseEntity<NativeTokens> nativeResponse(AuthSessionService.Tokens tokens) {
        return ResponseEntity.ok().header("Cache-Control", "no-store").body(new NativeTokens(tokens.accessToken(), tokens.refreshToken()));
    }
    private ResponseEntity<TokenResponse> cookieResponse(AuthSessionService.Tokens tokens, HttpServletResponse response) {
        cookies.addRefreshCookie(response, tokens.refreshToken(), tokens.refreshExpiresAt());
        response.setHeader("Cache-Control", "no-store");
        return ResponseEntity.ok(new TokenResponse(tokens.accessToken()));
    }
}
