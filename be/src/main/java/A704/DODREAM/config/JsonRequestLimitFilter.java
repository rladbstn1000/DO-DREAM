package A704.DODREAM.config;

import java.io.ByteArrayInputStream;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import jakarta.servlet.*;
import jakarta.servlet.http.*;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/** Bound JSON before Jackson allocation; form limits do not cover JSON or chunked JSON. */
@Component
@Order(Ordered.LOWEST_PRECEDENCE)
public class JsonRequestLimitFilter extends OncePerRequestFilter {
    public static final int MAX_BYTES = 2 * 1024 * 1024;

    @Override protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws IOException, ServletException {
        String contentType = request.getContentType();
        boolean json = false;
        if (contentType != null) {
            try {
                MediaType type = MediaType.parseMediaType(contentType);
                json = "application".equalsIgnoreCase(type.getType()) &&
                    ("json".equalsIgnoreCase(type.getSubtype()) || type.getSubtype().endsWith("+json"));
            } catch (IllegalArgumentException ignored) { /* Normal content negotiation rejects malformed types. */ }
        }
        if (!json) { chain.doFilter(request,response); return; }
        if (request.getContentLengthLong() > MAX_BYTES) { reject(response); return; }
        byte[] body = request.getInputStream().readNBytes(MAX_BYTES + 1);
        if (body.length > MAX_BYTES) { reject(response); return; }
        chain.doFilter(new HttpServletRequestWrapper(request) {
            @Override public ServletInputStream getInputStream() {
                var input = new ByteArrayInputStream(body);
                return new ServletInputStream() {
                    @Override public int read() { return input.read(); }
                    @Override public int read(byte[] b,int off,int len) { return input.read(b,off,len); }
                    @Override public boolean isFinished() { return input.available() == 0; }
                    @Override public boolean isReady() { return true; }
                    @Override public void setReadListener(ReadListener listener) {
                        throw new IllegalStateException("Only synchronous servlet request bodies are supported");
                    }
                };
            }
            @Override public BufferedReader getReader() throws IOException {
                return new BufferedReader(new InputStreamReader(getInputStream(),
                    getCharacterEncoding() == null ? StandardCharsets.UTF_8 : java.nio.charset.Charset.forName(getCharacterEncoding())));
            }
        },response);
    }

    private static void reject(HttpServletResponse response) throws IOException {
        response.setStatus(413);
        response.setContentType("application/json");
        response.setCharacterEncoding("UTF-8");
        response.getWriter().write("{\"code\":\"REQUEST_TOO_LARGE\",\"message\":\"요청 크기 제한을 초과했습니다.\"}");
    }
}
