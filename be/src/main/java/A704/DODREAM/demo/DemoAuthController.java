package A704.DODREAM.demo;

import A704.DODREAM.auth.dto.response.TokenResponse;
import A704.DODREAM.auth.util.*;
import com.fasterxml.jackson.databind.JsonNode;
import io.jsonwebtoken.JwtException;
import jakarta.servlet.http.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.time.Duration;
import java.util.*;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController @RequestMapping("/api/auth/demo")
public class DemoAuthController {
    static final String VISITOR_COOKIE="dodream_demo_visitor";
    private final ObjectProvider<LocalDemoService> demo;
    private final CookieUtil cookies;
    private final JwtUtil jwt;
    private final SecureRandom random=new SecureRandom();
    public DemoAuthController(ObjectProvider<LocalDemoService> demo,CookieUtil cookies,JwtUtil jwt) {this.demo=demo;this.cookies=cookies;this.jwt=jwt;}
    @GetMapping("/config") public LocalDemoService.Configuration configuration(HttpServletResponse response) {
        response.setHeader("Cache-Control","no-store");
        var enabled=demo.getIfAvailable();return enabled==null?LocalDemoService.disabled():enabled.configuration();
    }
    @PostMapping("/bootstrap") public Map<String,Boolean> bootstrap(@RequestBody JsonNode body,HttpServletRequest request,HttpServletResponse response) {
        enabled();empty(body);rejectSession(request);
        String value=visitor(request,false);
        if(value==null) {byte[] bytes=new byte[32];random.nextBytes(bytes);value=HexFormat.of().formatHex(bytes);}
        response.addHeader(HttpHeaders.SET_COOKIE,ResponseCookie.from(VISITOR_COOKIE,value).httpOnly(true).secure(cookies.secure())
            .sameSite("Lax").path("/api/auth/demo").maxAge(Duration.ofDays(14)).build().toString());
        response.setHeader("Cache-Control","no-store");return Map.of("ready",true);
    }
    @PostMapping("/start") public TokenResponse start(@RequestBody JsonNode body,HttpServletRequest request,HttpServletResponse response) {
        var service=enabled();empty(body);rejectSession(request);
        var tokens=service.start(hash(visitor(request,true)));
        cookies.addRefreshCookie(response,tokens.refreshToken(),tokens.refreshExpiresAt());
        response.setHeader("Cache-Control","no-store");return new TokenResponse(tokens.accessToken());
    }
    private LocalDemoService enabled() {var service=demo.getIfAvailable();if(service==null)throw LocalDemoStore.failure(404,"DEMO_DISABLED");return service;}
    static void empty(JsonNode body) {if(body==null || !body.isObject() || body.size()!=0)throw LocalDemoStore.failure(400,"INVALID_DEMO_REQUEST");}
    void rejectSession(HttpServletRequest request) {
        var auth=request.getHeader(HttpHeaders.AUTHORIZATION);
        if(auth!=null && auth.startsWith("Bearer ")) {
            try {jwt.parseAccess(auth.substring(7));throw LocalDemoStore.failure(409,"SESSION_ALREADY_PRESENT");}catch(JwtException ignored){}
        }
        if(request.getCookies()!=null) for(var cookie:request.getCookies()) if(CookieUtil.REFRESH_COOKIE.equals(cookie.getName())) {
            try {jwt.parseRefresh(cookie.getValue());throw LocalDemoStore.failure(409,"SESSION_ALREADY_PRESENT");}catch(JwtException ignored){}
        }
    }
    static String visitor(HttpServletRequest request,boolean required) {
        String value=null;
        if(request.getCookies()!=null)for(var cookie:request.getCookies())if(VISITOR_COOKIE.equals(cookie.getName())) {
            if(value!=null || !cookie.getValue().matches("[0-9a-f]{64}"))throw LocalDemoStore.failure(400,"INVALID_DEMO_VISITOR");value=cookie.getValue();
        }
        if(value==null && required)throw LocalDemoStore.failure(400,"DEMO_BOOTSTRAP_REQUIRED");return value;
    }
    static String hash(String value) {
        try {return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.US_ASCII)));}
        catch(NoSuchAlgorithmException impossible){throw new IllegalStateException(impossible);}
    }
}
