package A704.DODREAM.file.service;

import java.security.PrivateKey;
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import software.amazon.awssdk.services.cloudfront.CloudFrontUtilities;
import software.amazon.awssdk.services.cloudfront.model.CannedSignerRequest;

@Slf4j
@Service
@Profile("!local")
@RequiredArgsConstructor
public class CloudFrontService {

	private final CloudFrontUtilities cloudFrontUtilities;
	private final WebClient webClient;

	@Value("${aws.cloudfront.domain}")
	private String cloudFrontDomain;

	@Value("${aws.cloudfront.key-pair-id}")
	private String keyPairId;

	@Value("${aws.cloudfront.private-key-pem}")
	private String privateKeyPem;

	/**
	 * CloudFront signed URL 생성
	 */
	public String generateSignedUrl(String s3Key) {
		try {
			String resourceUrl = "https://" + cloudFrontDomain + "/" + s3Key;

			// Expiration time: 1 hour from now
			Instant expirationDate = Instant.now().plus(1, ChronoUnit.HOURS);

			String normalized = privateKeyPem.replace("\\n", "\n")
				.replace("-----BEGIN PRIVATE KEY-----", "")
				.replace("-----END PRIVATE KEY-----", "")
				.replaceAll("\\s", "");
			byte[] decodedKey = java.util.Base64.getDecoder().decode(normalized);
			PrivateKey privateKey = java.security.KeyFactory.getInstance("RSA")
				.generatePrivate(new java.security.spec.PKCS8EncodedKeySpec(decodedKey));
			CannedSignerRequest request = CannedSignerRequest.builder()
				.resourceUrl(resourceUrl)
				.privateKey(privateKey)
				.keyPairId(keyPairId)
				.expirationDate(expirationDate)
				.build();

			String signedUrl = cloudFrontUtilities.getSignedUrlWithCannedPolicy(request).url();

			log.info("Generated CloudFront signed URL for s3Key: {}", s3Key);

			return signedUrl;

		} catch (Exception e) {
			log.error("CloudFront signing failed type={}", e.getClass().getSimpleName());
			throw new RuntimeException("Failed to generate CloudFront signed URL", e);
		}
	}

	/**
	 * CloudFront를 통해 PDF 파일 다운로드
	 */
	public byte[] downloadFile(String s3Key) {
		try {
			String signedUrl = generateSignedUrl(s3Key);

			// Use WebClient or RestTemplate to download the file
			// For now, we'll use the signed URL directly
			log.info("Downloading file from CloudFront: {}", s3Key);

			// This will be implemented with WebClient
			return downloadFileFromUrl(signedUrl);

		} catch (Exception e) {
			log.error("CloudFront download failed type={}", e.getClass().getSimpleName());
			throw new RuntimeException("Failed to download file from CloudFront", e);
		}
	}

	private byte[] downloadFileFromUrl(String url) {
		try {
			// Signed URLs are bearer capabilities and must never enter logs.

			return webClient.get()
				.uri(url)
				.retrieve()
				.bodyToMono(byte[].class)
				.timeout(Duration.ofSeconds(15))
				.block(Duration.ofSeconds(15));

		} catch (Exception e) {
			log.error("CloudFront transport failed type={}", e.getClass().getSimpleName());
			throw new RuntimeException("Failed to download file", e);
		}
	}
}