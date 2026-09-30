package A704.DODREAM.demo;

import A704.DODREAM.auth.exception.AuthException;
import A704.DODREAM.auth.service.AuthSessionService;
import A704.DODREAM.auth.util.*;
import A704.DODREAM.config.SecurityConfig;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.jsonwebtoken.JwtException;
import jakarta.servlet.http.Cookie;
import java.time.Instant;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.mock.env.MockEnvironment;
import org.springframework.mock.web.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class DemoAuthTests {
    ObjectMapper json=new ObjectMapper();
    LocalDemoService service=mock(LocalDemoService.class);
    JwtUtil jwt=mock(JwtUtil.class);
    ObjectProvider<LocalDemoService> provider;
    DemoAuthController controller;
    @BeforeEach @SuppressWarnings("unchecked") void setup() {
        provider=mock(ObjectProvider.class);when(provider.getIfAvailable()).thenReturn(service);
        var env=new MockEnvironment();env.setActiveProfiles("local");controller=new DemoAuthController(provider,new CookieUtil(false,env),jwt);
    }
    @Test void disabledCannotBootstrapOrStartAndDoesNotConsultSessions() throws Exception {
        when(provider.getIfAvailable()).thenReturn(null);
        assertFalse(controller.configuration(new MockHttpServletResponse()).enabled());
        for(var route:new String[]{"bootstrap","start"}) {
            var failure=assertThrows(AuthException.class,()->{
                if(route.equals("bootstrap"))controller.bootstrap(json.readTree("{}"),new MockHttpServletRequest(),new MockHttpServletResponse());
                else controller.start(json.readTree("{}"),new MockHttpServletRequest(),new MockHttpServletResponse());});
            assertEquals(404,failure.status().value());
        }
        verifyNoInteractions(service,jwt);
    }
    @Test void bootstrapKeepsOpaqueSecretOnlyInScopedHttpOnlyCookie() throws Exception {
        var response=new MockHttpServletResponse();var result=controller.bootstrap(json.readTree("{}"),new MockHttpServletRequest(),response);
        assertEquals(java.util.Map.of("ready",true),result);
        String cookie=response.getHeader("Set-Cookie");
        assertTrue(cookie.contains("HttpOnly"));assertTrue(cookie.contains("Path=/api/auth/demo"));assertTrue(cookie.contains("SameSite=Lax"));
        assertTrue(cookie.matches("dodream_demo_visitor=[0-9a-f]{64};.*"));assertEquals("no-store",response.getHeader("Cache-Control"));
        verifyNoInteractions(service);
    }
    @Test void bootstrapReusesVisitorAndDoesNotAllocateAnotherIdentity() throws Exception {
        var request=new MockHttpServletRequest();request.setCookies(new Cookie(DemoAuthController.VISITOR_COOKIE,"a".repeat(64)));
        var response=new MockHttpServletResponse();controller.bootstrap(json.readTree("{}"),request,response);
        assertTrue(response.getHeader("Set-Cookie").startsWith(DemoAuthController.VISITOR_COOKIE+"="+"a".repeat(64)+";"));
    }
    @Test void forgedAuthorityBodyAndMalformedOrDuplicateVisitorAreRejected() throws Exception {
        assertThrows(AuthException.class,()->controller.start(json.readTree("{\"userId\":1}"),new MockHttpServletRequest(),new MockHttpServletResponse()));
        for(var cookies:new Cookie[][]{{new Cookie(DemoAuthController.VISITOR_COOKIE,"bad")},{new Cookie(DemoAuthController.VISITOR_COOKIE,"a".repeat(64)),new Cookie(DemoAuthController.VISITOR_COOKIE,"a".repeat(64))}}) {
            var request=new MockHttpServletRequest();request.setCookies(cookies);
            assertThrows(AuthException.class,()->controller.start(json.readTree("{}"),request,new MockHttpServletResponse()));
        }
        verifyNoInteractions(service);
    }
    @Test void existingAccessOrRefreshRejectsBeforeAccountCreationWithoutCookieMutation() throws Exception {
        for(boolean refresh:new boolean[]{true,false}) {
            var request=new MockHttpServletRequest();
            if(refresh)request.setCookies(new Cookie("refresh","signed-valid"));else request.addHeader("Authorization","Bearer signed-valid");
            var response=new MockHttpServletResponse();
            var e=assertThrows(AuthException.class,()->controller.start(json.readTree("{}"),request,response));
            assertEquals("SESSION_ALREADY_PRESENT",e.code());assertEquals(409,e.status().value());assertNull(response.getHeader("Set-Cookie"));
        }
        verifyNoInteractions(service);
    }
    @Test void startHashesVisitorAndReturnsOnlyAccessTokenWithRealSessionCookieContract() throws Exception {
        var request=new MockHttpServletRequest();request.setCookies(new Cookie(DemoAuthController.VISITOR_COOKIE,"a".repeat(64)));
        when(service.start(DemoAuthController.hash("a".repeat(64)))).thenReturn(new AuthSessionService.Tokens("at","rt",Instant.now().plusSeconds(120)));
        var response=new MockHttpServletResponse();var result=controller.start(json.readTree("{}"),request,response);
        assertEquals("at",result.accessToken());assertTrue(response.getHeader("Set-Cookie").startsWith("refresh=rt;"));
        assertTrue(response.getHeader("Set-Cookie").contains("Path=/api/auth;"));assertTrue(response.getHeader("Set-Cookie").contains("HttpOnly"));
        assertNotEquals("a".repeat(64),DemoAuthController.hash("a".repeat(64)));
    }
    @Test void redisUnavailableProducesNoRefreshCookie() throws Exception {
        var request=new MockHttpServletRequest();request.setCookies(new Cookie(DemoAuthController.VISITOR_COOKIE,"a".repeat(64)));
        when(service.start(anyString())).thenThrow(AuthException.unavailable());var response=new MockHttpServletResponse();
        assertEquals(503,assertThrows(AuthException.class,()->controller.start(json.readTree("{}"),request,response)).status().value());
        assertNull(response.getHeader("Set-Cookie"));
    }
    @Test void expiredCredentialsDoNotBlockAnExplicitNewDemoStart() {
        when(jwt.parseRefresh(anyString())).thenThrow(new JwtException("expired"));
        var request=new MockHttpServletRequest();request.setCookies(new Cookie("refresh","expired"));
        assertDoesNotThrow(()->controller.rejectSession(request));
    }
    @Test void bothNewMutationsRequireCsrfUsingDecodedRoute() {
        for(var route:new String[]{"bootstrap","start"}) {
            var request=new MockHttpServletRequest("POST","/api/auth/demo/%73tart");request.setServletPath("/api/auth/demo/"+route);
            assertTrue(SecurityConfig.isCookieAuthMutation(request));
        }
    }
}
