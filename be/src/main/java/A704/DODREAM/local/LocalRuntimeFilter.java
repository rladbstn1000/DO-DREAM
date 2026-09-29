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
        String path = request.getRequestURI();
        boolean unavailable = path.equals("/api/files/presigned-url") || path.equals("/api/files/upload")
            || path.equals("/api/pdf/upload-and-parse") || path.matches("/api/documents/[^/]+/publish")
            || path.matches("/api/pdf/[^/]+/json-url");
        if (unavailable && !"OPTIONS".equals(request.getMethod())) {
            response.setStatus(503);
            response.setContentType("application/json;charset=UTF-8");
            mapper.writeValue(response.getOutputStream(), Map.of("code", "LOCAL_EXTERNAL_DISABLED",
                "local_fixture", true, "message", "External upload, parsing and publishing are unavailable in local mode. Use the seeded synthetic lesson."));
            return;
        }
        chain.doFilter(request, response);
    }
}
