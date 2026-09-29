package A704.DODREAM.local;

import org.springframework.context.annotation.Profile;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile("local")
public class LocalFixtureController {
    // This route uses the existing authenticated catch-all security rule.
    @GetMapping(value = "/api/local/fixtures/lesson.json", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<byte[]> lesson() {
        return ResponseEntity.ok().header("X-DO-DREAM-Mode", "local-synthetic-fixture")
            .body(LocalExternalConfiguration.fixture(LocalExternalConfiguration.FIXTURE_KEY));
    }
}
