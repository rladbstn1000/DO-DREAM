package A704.DODREAM.demo;

import A704.DODREAM.auth.dto.request.UserPrincipal;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController @Profile("local") @ConditionalOnProperty(name="LOCAL_DEMO_ENABLED",havingValue="true")
@RequestMapping("/api/demo")
public class DemoPreparationController {
    private final LocalDemoService demo;
    public DemoPreparationController(LocalDemoService demo){this.demo=demo;}
    @GetMapping("/preparation") public Object state(@AuthenticationPrincipal UserPrincipal user){return demo.preparation(user.userId());}
    @PostMapping("/prepare") public Object prepare(@AuthenticationPrincipal UserPrincipal user,@RequestBody JsonNode body){DemoAuthController.empty(body);return demo.prepare(user.userId());}
}
