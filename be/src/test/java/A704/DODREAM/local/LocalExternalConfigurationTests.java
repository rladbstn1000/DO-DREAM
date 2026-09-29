package A704.DODREAM.local;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

import static org.junit.jupiter.api.Assertions.*;

class LocalExternalConfigurationTests {
    private final LocalExternalConfiguration configuration = new LocalExternalConfiguration();

    @Test
    void syntheticStorageReadsOnlyTheNamedFixture() throws Exception {
        try (var storage = configuration.s3Client();
             var data = storage.getObject(GetObjectRequest.builder()
                 .bucket("local-synthetic-fixtures").key(LocalExternalConfiguration.FIXTURE_KEY).build())) {
            assertTrue(new String(data.readAllBytes(), StandardCharsets.UTF_8).contains("\"local_fixture\": true"));
            assertThrows(ResponseStatusException.class, () -> storage.getObject(
                GetObjectRequest.builder().bucket("local-synthetic-fixtures").key("unavailable.json").build()));
        }
    }

    @Test
    void storageWritesFailInsteadOfReportingSuccess() {
        try (var storage = configuration.s3Client()) {
            assertThrows(ResponseStatusException.class, () -> storage.putObject(
                PutObjectRequest.builder().bucket("local-synthetic-fixtures").key("anything").build(),
                RequestBody.fromString("test")));
        }
    }

    @Test
    void externalHttpRequestIsRejectedBeforeNetworkIo() {
        var client = configuration.webClient("http://ai:8000");
        assertThrows(ResponseStatusException.class, () -> client.get().uri("https://example.invalid/data")
            .retrieve().bodyToMono(String.class).block(Duration.ofSeconds(1)));
    }

    @Test
    void localProfileRejectsExternalAiOrigin() {
        assertThrows(IllegalStateException.class, () -> configuration.webClient("https://provider.invalid"));
    }
}
