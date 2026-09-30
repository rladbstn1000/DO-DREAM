package A704.DODREAM.auth;

import A704.DODREAM.auth.filter.JwtAuthFilter;
import A704.DODREAM.auth.util.JwtUtil;
import A704.DODREAM.config.SecurityConfig;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class AuthRoutingTests {
    @ParameterizedTest
    @ValueSource(strings = {"teacher/login", "teacher/refresh", "teacher/logout", "student/login", "student/refresh", "student/logout"})
    void csrfMatchesDecodedCookieRoutesIncludingEncodedRawUris(String route) {
        var request = new MockHttpServletRequest("POST", "/api/%61uth/" + route.replace("r", "%72"));
        request.setServletPath("/api/auth/" + route);
        assertTrue(SecurityConfig.isCookieAuthMutation(request));
        request.setMethod("GET");
        assertFalse(SecurityConfig.isCookieAuthMutation(request));
    }
    @Test
    void explicitlyAuthenticatedNativeRoutesRemainSeparate() {
        var request = new MockHttpServletRequest("POST", "/api/auth/student/native/refresh");
        request.setServletPath("/api/auth/student/native/refresh");
        assertFalse(SecurityConfig.isCookieAuthMutation(request));
    }
    @Test
    void encodedAuthPathDoesNotLetAnExpiredAccessHeaderBlockRefresh() throws Exception {
        JwtUtil jwt = mock(JwtUtil.class);
        var request = new MockHttpServletRequest("POST", "/api/%61uth/teacher/%72efresh");
        request.setServletPath("/api/auth/teacher/refresh");
        request.addHeader("Authorization", "Bearer invalid-test-access");
        var chain = new MockFilterChain();
        new JwtAuthFilter(jwt).doFilter(request, new MockHttpServletResponse(), chain);
        assertNotNull(chain.getRequest());
        verifyNoInteractions(jwt);
    }
}
