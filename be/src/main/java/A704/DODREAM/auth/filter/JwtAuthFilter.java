package A704.DODREAM.auth.filter;

import java.io.IOException;
import java.util.List;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import A704.DODREAM.auth.dto.request.UserPrincipal;
import A704.DODREAM.auth.util.JwtUtil;
import io.jsonwebtoken.Claims;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;

@Component
@RequiredArgsConstructor
public class JwtAuthFilter extends OncePerRequestFilter {

	private final JwtUtil jwt;

	@Override
	protected boolean shouldNotFilter(HttpServletRequest request) {
        // Cookie/body authentication validates its own refresh token; expired AT must not block it.
        // Use the decoded routing path so encoded auth URLs follow exactly the same policy.
        String path = request.getServletPath();
		if(path.startsWith("/api/auth/")
            || path.startsWith("/api/actuator")
				|| path.startsWith("/actuator")) {
			return true;
		}
		return "OPTIONS".equalsIgnoreCase(request.getMethod());
	}

	@Override
	protected void doFilterInternal(HttpServletRequest req, HttpServletResponse res, FilterChain chain)
		throws ServletException, IOException {
		String h = req.getHeader("Authorization");
		if (h != null && h.startsWith("Bearer ")) {
			try {
				Claims c = jwt.parseAccess(h.substring(7)).getPayload();

				// JwtUtil에서 subject = userId 문자열, name/role은 claim으로 발급 중
				Long userId = parseLong(c.getSubject());
				String name = c.get("name", String.class);
				String role = c.get("role", String.class);

				if (userId == null || role == null) {
					res.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
					return;
				}

				if (SecurityContextHolder.getContext().getAuthentication() == null) {
					UserPrincipal principal = new UserPrincipal(userId, name, role);

					var auth = new UsernamePasswordAuthenticationToken(
						principal,
						null,
						List.of(new SimpleGrantedAuthority("ROLE_" + role))
					);
					SecurityContextHolder.getContext().setAuthentication(auth);
				}
			} catch (Exception e) {
				res.setStatus(HttpServletResponse.SC_UNAUTHORIZED); // 401
				return;
			}
		}
		chain.doFilter(req, res);
	}

	private Long parseLong(String v) {
		try {
			return v == null ? null : Long.parseLong(v);
		} catch (NumberFormatException e) {
			return null;
		}
	}
}
