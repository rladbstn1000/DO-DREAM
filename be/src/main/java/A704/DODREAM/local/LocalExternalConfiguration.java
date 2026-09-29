package A704.DODREAM.local;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.lang.reflect.Proxy;

import A704.DODREAM.fcm.dto.FcmResponse;
import A704.DODREAM.fcm.dto.FcmSendRequest;
import A704.DODREAM.fcm.repository.UserDevicesRepository;
import A704.DODREAM.fcm.service.FcmService;
import A704.DODREAM.file.dto.PageOcrResult;
import A704.DODREAM.file.service.ClovaOcrService;
import A704.DODREAM.file.service.CloudFrontService;
import A704.DODREAM.user.repository.UserRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.io.ClassPathResource;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;

/** Only provider boundaries are replaced. Authentication, domain services, MySQL and Redis stay real. */
@Configuration
@Profile("local")
public class LocalExternalConfiguration {
    public static final String FIXTURE_KEY = "local/synthetic/lesson.json";

    public static byte[] fixture(String key) {
        if (!FIXTURE_KEY.equals(key)) {
            throw unavailable("Only the synthetic local lesson is available");
        }
        try (var stream = new ClassPathResource("local/lesson.json").getInputStream()) {
            return stream.readAllBytes();
        } catch (IOException ex) {
            throw new IllegalStateException("Missing synthetic local fixture", ex);
        }
    }

    private static ResponseStatusException unavailable(String reason) {
        return new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
            "LOCAL_EXTERNAL_DISABLED: " + reason);
    }

    @Bean
    WebClient webClient(@org.springframework.beans.factory.annotation.Value("${fastapi.url}") String aiUrl) {
        java.net.URI allowed = java.net.URI.create(aiUrl);
        if (!java.util.Set.of("ai", "python-service", "127.0.0.1", "localhost").contains(allowed.getHost())
            || !"http".equals(allowed.getScheme())) {
            throw new IllegalStateException("Local AI URL must point to the isolated local service");
        }
        return WebClient.builder().filter((request, next) -> {
            java.net.URI uri = request.url();
            if (!allowed.getScheme().equals(uri.getScheme()) || !allowed.getHost().equals(uri.getHost())
                || allowed.getPort() != uri.getPort()) {
                return reactor.core.publisher.Mono.error(unavailable("External HTTP requests are blocked"));
            }
            return next.exchange(request);
        }).build();
    }

    @Bean
    WebClient branchWebClient() {
        return WebClient.builder().filter((request, next) ->
            reactor.core.publisher.Mono.error(unavailable("Branch calls are disabled"))).build();
    }

    @Bean
    S3Client s3Client() {
        // A narrow, read-only object-storage adapter; no AWS SDK network client is constructed.
        return (S3Client) Proxy.newProxyInstance(S3Client.class.getClassLoader(), new Class<?>[]{S3Client.class},
            (proxy, method, args) -> {
                if (method.getName().equals("close")) return null;
                if (method.getName().equals("serviceName")) return "local-synthetic-storage";
                if (method.getName().equals("toString")) return "LocalSyntheticS3Boundary";
                if (method.getName().equals("hashCode")) return System.identityHashCode(proxy);
                if (method.getName().equals("equals")) return proxy == args[0];
                if (method.getName().equals("getObject") && args.length == 1 && args[0] instanceof GetObjectRequest request) {
                    byte[] bytes = fixture(request.key());
                    return new ResponseInputStream<>(GetObjectResponse.builder()
                        .contentType("application/json").contentLength((long) bytes.length).build(),
                        new ByteArrayInputStream(bytes));
                }
                throw unavailable("Object-storage writes and non-fixture reads are unavailable");
            });
    }

    @Bean
    S3Presigner s3Presigner() {
        return (S3Presigner) Proxy.newProxyInstance(S3Presigner.class.getClassLoader(), new Class<?>[]{S3Presigner.class},
            (proxy, method, args) -> {
                if (method.getName().equals("close")) return null;
                if (method.getName().equals("toString")) return "LocalDisabledPresigner";
                if (method.getName().equals("hashCode")) return System.identityHashCode(proxy);
                if (method.getName().equals("equals")) return proxy == args[0];
                throw unavailable("Uploads are unavailable; use the seeded synthetic lesson");
            });
    }

    @Bean
    CloudFrontService cloudFrontService(WebClient webClient) {
        return new CloudFrontService(null, webClient) {
            @Override
            public String generateSignedUrl(String key) {
                fixture(key); // Reject every object outside the single synthetic fixture.
                return "/api/local/fixtures/lesson.json?local_fixture=true";
            }
            @Override
            public byte[] downloadFile(String key) { return fixture(key); }
        };
    }

    @Bean
    ClovaOcrService clovaOcrService(WebClient webClient) {
        return new ClovaOcrService(webClient) {
            @Override
            public PageOcrResult processImage(java.io.File imageFile, int pageNumber) {
                throw unavailable("OCR is unavailable in the local profile");
            }
        };
    }

    @Bean
    FcmService fcmService(UserRepository users, UserDevicesRepository devices) {
        return new FcmService(users, devices) {
            @Override
            public void initialize() { /* Local profile never loads Firebase credentials. */ }
            @Override
            public FcmResponse sendMessageTo(FcmSendRequest request) {
                return FcmResponse.builder().success(false)
                    .message("LOCAL_EXTERNAL_DISABLED: Firebase notifications are unavailable").build();
            }
        };
    }
}
