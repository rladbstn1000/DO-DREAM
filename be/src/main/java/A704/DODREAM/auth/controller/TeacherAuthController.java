package A704.DODREAM.auth.controller;

import A704.DODREAM.auth.dto.request.TeacherLoginRequest;
import A704.DODREAM.auth.dto.request.TeacherSignupRequest;
import A704.DODREAM.auth.dto.request.TeacherVerifyRequest;
import A704.DODREAM.auth.dto.response.TokenResponse;
import A704.DODREAM.auth.service.AuthSessionService;
import A704.DODREAM.auth.service.TeacherAuthService;
import A704.DODREAM.auth.util.CookieUtil;
import A704.DODREAM.user.entity.Role;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@io.swagger.v3.oas.annotations.tags.Tag(name = "Teacher Auth API", description = "교사 인증 API")
@RestController
@RequestMapping("/api/auth/teacher")
@RequiredArgsConstructor
public class TeacherAuthController {
    private final TeacherAuthService teacherAuthService;
    private final AuthSessionService sessions;
    private final CookieUtil cookies;

    @io.swagger.v3.oas.annotations.Operation(summary = "사전 인증")
    @PostMapping("/verify")
    public ResponseEntity<Void> verify(@RequestBody TeacherVerifyRequest request) {
        teacherAuthService.verify(request);
        return ResponseEntity.ok().build();
    }
    @io.swagger.v3.oas.annotations.Operation(summary = "회원가입")
    @PostMapping("/register")
    public ResponseEntity<Void> register(@RequestBody TeacherSignupRequest request) {
        teacherAuthService.signup(request);
        return ResponseEntity.ok().build();
    }
    @io.swagger.v3.oas.annotations.Operation(summary = "로그인: Access Token 응답 / Refresh Token HttpOnly 쿠키")
    @PostMapping("/login")
    public ResponseEntity<TokenResponse> login(@RequestBody TeacherLoginRequest request, HttpServletResponse response) {
        return cookieResponse(sessions.login(teacherAuthService.authenticate(request)), response);
    }
    @io.swagger.v3.oas.annotations.Operation(summary = "쿠키 Refresh Token 원자 회전")
    @PostMapping("/refresh")
    public ResponseEntity<TokenResponse> refresh(HttpServletRequest request, HttpServletResponse response) {
        return cookieResponse(sessions.refresh(cookies.refreshFrom(request), Role.TEACHER), response);
    }
    @io.swagger.v3.oas.annotations.Operation(summary = "현재 사용자 Refresh 세션 폐기")
    @PostMapping("/logout")
    public ResponseEntity<Void> logout(HttpServletRequest request, HttpServletResponse response) {
        sessions.logout(cookies.refreshFrom(request), Role.TEACHER);
        cookies.deleteRefreshCookie(response);
        return ResponseEntity.ok().build();
    }
    private ResponseEntity<TokenResponse> cookieResponse(AuthSessionService.Tokens tokens, HttpServletResponse response) {
        cookies.addRefreshCookie(response, tokens.refreshToken(), tokens.refreshExpiresAt());
        response.setHeader("Cache-Control", "no-store");
        return ResponseEntity.ok(new TokenResponse(tokens.accessToken()));
    }
}
