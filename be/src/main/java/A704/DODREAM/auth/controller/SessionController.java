package A704.DODREAM.auth.controller;

import A704.DODREAM.auth.dto.request.UserPrincipal;
import A704.DODREAM.authorization.AuthorizationPolicy;
import A704.DODREAM.demo.LocalDemoService;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController @RequestMapping("/api/session")
public class SessionController {
    private final AuthorizationPolicy policy;
    private final ObjectProvider<LocalDemoService> demo;
    public SessionController(AuthorizationPolicy policy,ObjectProvider<LocalDemoService> demo){this.policy=policy;this.demo=demo;}
    public record Session(long userId,String name,String role,boolean demo){}
    @GetMapping("/me") public Session me(@AuthenticationPrincipal UserPrincipal principal) {
        var user=policy.actor(principal.userId());var service=demo.getIfAvailable();
        return new Session(user.getId(),user.getName(),user.getRole().name(),service!=null && service.isDemo(user.getId()));
    }
}
