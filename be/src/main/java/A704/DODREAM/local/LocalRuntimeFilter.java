package A704.DODREAM.local;

import java.io.IOException;
import java.util.Map;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/** Explicit unavailable responses for provider writes; existing Spring Security still applies. */
@Component
@Profile("local")
@RequiredArgsConstructor
public class LocalRuntimeFilter extends OncePerRequestFilter {
    private final ObjectMapper mapper;

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
        throws ServletException, IOException {
        response.setHeader("X-DO-DREAM-Mode", "local-synthetic-provider-boundaries");
        // Controllers enforce identity/ownership before reaching a provider boundary. The boundary
        // itself rejects unsupported operations, so denied callers never learn provider state.
        chain.doFilter(request, response);
    }
}
