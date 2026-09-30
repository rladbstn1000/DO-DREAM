package A704.DODREAM.indexing;

import A704.DODREAM.auth.dto.request.UserPrincipal;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
public class IndexingController {
    private final IndexingStore store;
    private final IndexingService service;
    public IndexingController(IndexingStore store,IndexingService service) { this.store=store; this.service=service; }
    @GetMapping("/api/documents/{id}/indexing")
    public IndexingSummary material(@AuthenticationPrincipal UserPrincipal user,@PathVariable long id) { return store.resource(user.userId(),"MATERIAL",id); }
    @GetMapping("/api/pdf/{id}/indexing")
    public IndexingSummary pdf(@AuthenticationPrincipal UserPrincipal user,@PathVariable long id) { return store.resource(user.userId(),"PDF",id); }
    @PostMapping("/api/documents/{id}/indexing")
    public IndexingSummary requestMaterial(@AuthenticationPrincipal UserPrincipal user,@PathVariable long id,@RequestBody(required=false) JsonNode body) { return service.request(user.userId(),"MATERIAL",id,spec(body)); }
    @PostMapping("/api/pdf/{id}/indexing")
    public IndexingSummary requestPdf(@AuthenticationPrincipal UserPrincipal user,@PathVariable long id,@RequestBody(required=false) JsonNode body) { return service.request(user.userId(),"PDF",id,spec(body)); }
    @GetMapping("/api/indexing/jobs/{jobId}")
    public IndexingSummary job(@AuthenticationPrincipal UserPrincipal user,@PathVariable String jobId) { return store.job(user.userId(),jobId); }
    @PostMapping("/api/indexing/jobs/{jobId}/retry")
    public IndexingSummary retry(@AuthenticationPrincipal UserPrincipal user,@PathVariable String jobId,@RequestBody JsonNode body) {
        if(!body.isObject() || body.size()!=1 || !body.path("expectedGeneration").isIntegralNumber()
            || !body.path("expectedGeneration").canConvertToInt()) throw IndexingSource.invalid();
        return store.retry(user.userId(),jobId,body.path("expectedGeneration").intValue());
    }
    private static String spec(JsonNode body) {
        if(body==null) return null;
        if(!body.isObject() || body.size()>1 || (body.size()==1 && !body.path("indexSpec").isTextual())) throw IndexingSource.invalid();
        return body.path("indexSpec").textValue();
    }
}
