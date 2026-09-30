package A704.DODREAM.hardening;

import A704.DODREAM.auth.filter.JwtAuthFilter;
import A704.DODREAM.auth.util.CookieUtil;
import A704.DODREAM.auth.util.JwtUtil;
import A704.DODREAM.config.SecurityConfig;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.*;
import org.springframework.core.env.Environment;
import org.springframework.mock.env.MockEnvironment;
import org.springframework.mock.web.MockServletContext;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
import org.springframework.web.bind.annotation.*;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import static org.mockito.Mockito.mock;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** Exercise the real security filter chain without any Vault/database/provider startup. */
class SecurityExposureTests {
    @Test void normalProfileExposesOnlyHealthAndRejectsLocalBrowserOrigin() throws Exception {
        try (var context=context(false)) {
            var mvc=MockMvcBuilders.webAppContextSetup(context).apply(springSecurity()).build();
            mvc.perform(get("/actuator/health")).andExpect(status().isOk());
            mvc.perform(get("/actuator/metrics")).andExpect(status().is4xxClientError());
            mvc.perform(get("/api/actuator/prometheus")).andExpect(status().is4xxClientError());
            mvc.perform(get("/api/v3/api-docs")).andExpect(status().is4xxClientError());
            mvc.perform(get("/document/parse-pdf-from-cloudfront")).andExpect(status().is4xxClientError());
            mvc.perform(get("/actuator/health").header("Origin","http://localhost:5173")).andExpect(status().isForbidden());
        }
    }
    @Test void localProfileExplicitlyAllowsDocsAndLocalOriginButStillDeniesMetrics() throws Exception {
        try (var context=context(true)) {
            var mvc=MockMvcBuilders.webAppContextSetup(context).apply(springSecurity()).build();
            mvc.perform(get("/api/v3/api-docs")).andExpect(status().isOk());
            mvc.perform(get("/actuator/metrics")).andExpect(status().is4xxClientError());
            mvc.perform(get("/actuator/health").header("Origin","http://localhost:5173"))
                .andExpect(status().isOk()).andExpect(header().string("Access-Control-Allow-Origin","http://localhost:5173"));
        }
    }
    private AnnotationConfigWebApplicationContext context(boolean local) {
        var context=new AnnotationConfigWebApplicationContext();
        var environment=new MockEnvironment(); if(local) environment.setActiveProfiles("local");
        context.setEnvironment(environment); context.setServletContext(new MockServletContext());
        context.register(ProbeConfiguration.class,SecurityConfig.class); context.refresh(); return context;
    }
    @Configuration @EnableWebSecurity @EnableWebMvc
    static class ProbeConfiguration {
        @Bean CookieUtil cookies(Environment env) { return new CookieUtil(true,env); }
        @Bean JwtAuthFilter jwt() { return new JwtAuthFilter(mock(JwtUtil.class)); }
        @Bean ProbeController probe() { return new ProbeController(); }
    }
    @RestController
    static class ProbeController {
        @GetMapping({"/actuator/health","/actuator/metrics","/api/actuator/prometheus","/api/v3/api-docs","/document/parse-pdf-from-cloudfront"})
        String probe() { return "{}"; }
    }
}
