package A704.DODREAM.demo;

import A704.DODREAM.auth.dto.request.UserPrincipal;
import A704.DODREAM.authorization.AuthorizationPolicy;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController @Profile("local") @ConditionalOnProperty(name={"LOCAL_DEMO_ENABLED","LOCAL_PHASE5_ENABLED"},havingValue="true")
@RequestMapping("/api/demo/phase5")
public class Phase5PreparationController {
    private final Phase5Service service;
    public Phase5PreparationController(Phase5Service service){this.service=service;}
    @PostMapping("/prepare") public Phase5Service.Result prepare(@AuthenticationPrincipal UserPrincipal user,@RequestBody JsonNode body) {
        if(body==null || !body.isObject() || body.size()>(body.has("studentId")?1:0))throw AuthorizationPolicy.invalid();
        Long student=null;
        if(body.has("studentId")) {
            var value=body.get("studentId");
            if(!value.isIntegralNumber() || !value.canConvertToLong() || value.longValue()<=0)throw AuthorizationPolicy.invalid();
            student=value.longValue();
        }
        return service.prepare(user.userId(),student);
    }
}
