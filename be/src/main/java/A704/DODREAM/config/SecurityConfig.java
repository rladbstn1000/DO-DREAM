package A704.DODREAM.config;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;


import A704.DODREAM.auth.filter.JwtAuthFilter;
import A704.DODREAM.auth.util.CookieUtil;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import lombok.RequiredArgsConstructor;

@Configuration
@RequiredArgsConstructor
public class SecurityConfig {

	private final org.springframework.core.env.Environment environment;
	private final CookieUtil cookies;
	private final JwtAuthFilter jwtAuthFilter; // 분리한 필터 주입

	@Bean
	public CorsConfigurationSource corsConfigurationSource() {
		CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(environment.acceptsProfiles(org.springframework.core.env.Profiles.of("local", "test"))
            ? List.of("http://localhost:5173", "http://localhost:8080")
            : List.of("https://www.dodream.io.kr"));
		config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"));
		config.setAllowedHeaders(List.of("*"));
		config.setAllowCredentials(true);
		config.setMaxAge(3600L);

		UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
		source.registerCorsConfiguration("/**", config);
		return source;
	}

    public static boolean isCookieAuthMutation(jakarta.servlet.http.HttpServletRequest request) {
        // Match the servlet's decoded routing path, not its potentially percent-encoded raw URI.
        return "POST".equals(request.getMethod()) && request.getServletPath().matches(
            "/api/auth/((teacher|student)/(login|refresh|logout)|demo/(bootstrap|start))");
    }

    @Bean
    CookieCsrfTokenRepository csrfRepository() {
        CookieCsrfTokenRepository repository = new CookieCsrfTokenRepository();
        repository.setCookieCustomizer(cookie -> cookie.httpOnly(true).secure(cookies.secure())
            .path("/api/auth").sameSite("Lax"));
        return repository;
    }

	@Bean
	SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
		http
			.cors(c -> c.configurationSource(corsConfigurationSource()))
			.csrf(cs -> cs
                .csrfTokenRepository(csrfRepository())
                .csrfTokenRequestHandler(new CsrfTokenRequestAttributeHandler())
                .requireCsrfProtectionMatcher(SecurityConfig::isCookieAuthMutation))
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint((request, response, exception) -> response.sendError(401))
                .accessDeniedHandler((request, response, exception) -> response.sendError(403)))
			.sessionManagement(sm -> sm.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
			.authorizeHttpRequests(auth -> auth
				.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/actuator/health", "/api/actuator/health").permitAll()
                .requestMatchers("/actuator/**", "/api/actuator/**").denyAll()
				// 인가 규칙(화이트리스트)은 여기에서만 관리
        .requestMatchers("/api/pdf/**", "/api/files/**", "/api/documents/**").authenticated()

				.requestMatchers("/error", "/error/**").permitAll()
				.requestMatchers(
					"/api/swagger-ui/**", "/api/v3/api-docs/**",
					"/swagger-ui/**", "/v3/api-docs/**",
					"/swagger-resources/**"
                ).access((authentication, context) -> new org.springframework.security.authorization.AuthorizationDecision(
                    environment.acceptsProfiles(org.springframework.core.env.Profiles.of("local", "test"))))
                .requestMatchers("/api/auth/**", "/auth/**", "/health").permitAll()
        .requestMatchers("/api/test/**").denyAll()
				// 교사 전용
				.requestMatchers("/api/teacher/**").hasRole("TEACHER")
							.requestMatchers("/api/students/**").authenticated()
				// 나머지는 인증 필요
				.anyRequest().authenticated()
			)
			.addFilterBefore(jwtAuthFilter,
				org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter.class);

		return http.build();
	}
}