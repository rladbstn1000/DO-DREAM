package A704.DODREAM.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.cloudfront.CloudFrontClient;
import software.amazon.awssdk.services.cloudfront.CloudFrontUtilities;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;

@Configuration
@Profile("!local")
public class AWSConfig {

	@Value("${aws.s3.region}")
	private String region;

	@Value("${aws.access-key-id:}")
	private String accessKeyId;

	@Value("${aws.secret-access-key:}")
	private String secretAccessKey;

    @Bean(destroyMethod = "close")
    public software.amazon.awssdk.http.SdkHttpClient storageHttpClient() {
        // Reuse the locked SDK HTTP provider (Apache); no client/global timeout defaults.
        var provider=java.util.ServiceLoader.load(software.amazon.awssdk.http.SdkHttpService.class)
            .findFirst().orElseThrow(() -> new IllegalStateException("AWS HTTP transport is unavailable"));
        var defaults=software.amazon.awssdk.utils.AttributeMap.builder()
            .put(software.amazon.awssdk.http.SdkHttpConfigurationOption.CONNECTION_TIMEOUT,java.time.Duration.ofSeconds(2))
            .put(software.amazon.awssdk.http.SdkHttpConfigurationOption.CONNECTION_ACQUIRE_TIMEOUT,java.time.Duration.ofSeconds(2))
            .put(software.amazon.awssdk.http.SdkHttpConfigurationOption.READ_TIMEOUT,java.time.Duration.ofSeconds(5))
            .put(software.amazon.awssdk.http.SdkHttpConfigurationOption.WRITE_TIMEOUT,java.time.Duration.ofSeconds(5))
            .build();
        return provider.createHttpClientBuilder().buildWithDefaults(defaults);
    }

    private software.amazon.awssdk.core.client.config.ClientOverrideConfiguration storageTimeouts() {
        return software.amazon.awssdk.core.client.config.ClientOverrideConfiguration.builder()
            .apiCallTimeout(java.time.Duration.ofSeconds(15)).apiCallAttemptTimeout(java.time.Duration.ofSeconds(10))
            .retryPolicy(software.amazon.awssdk.core.retry.RetryPolicy.none()).build();
    }

	@Bean
	public S3Client s3Client(software.amazon.awssdk.http.SdkHttpClient storageHttpClient) {

		if (accessKeyId != null && !accessKeyId.isEmpty() && secretAccessKey != null && !secretAccessKey.isEmpty()) {
			return S3Client.builder().httpClient(storageHttpClient).overrideConfiguration(storageTimeouts())
				.region(Region.of(region))
				.credentialsProvider(StaticCredentialsProvider.create(
					AwsBasicCredentials.create(accessKeyId, secretAccessKey)))
				.build();
		}

		// Default credential provider chain (IAM role, environment variables, etc.)
		return S3Client.builder().httpClient(storageHttpClient).overrideConfiguration(storageTimeouts())
			.region(Region.of(region))
			.build();
	}

	@Bean
	public S3Presigner s3Presigner() {
		if (accessKeyId != null && !accessKeyId.isEmpty() && secretAccessKey != null && !secretAccessKey.isEmpty()) {
			return S3Presigner.builder()
				.region(Region.of(region))
				.credentialsProvider(StaticCredentialsProvider.create(
					AwsBasicCredentials.create(accessKeyId, secretAccessKey)))
				.build();
		}

		return S3Presigner.builder()
			.region(Region.of(region))
			.build();
	}

	@Bean
	public CloudFrontClient cloudFrontClient(software.amazon.awssdk.http.SdkHttpClient storageHttpClient) {
		if (accessKeyId != null && !accessKeyId.isEmpty() && secretAccessKey != null && !secretAccessKey.isEmpty()) {
			return CloudFrontClient.builder().httpClient(storageHttpClient).overrideConfiguration(storageTimeouts())
				.region(Region.AWS_GLOBAL)
				.credentialsProvider(StaticCredentialsProvider.create(
					AwsBasicCredentials.create(accessKeyId, secretAccessKey)))
				.build();
		}

		return CloudFrontClient.builder().httpClient(storageHttpClient).overrideConfiguration(storageTimeouts())
			.region(Region.AWS_GLOBAL)
			.build();
	}

	@Bean
	public CloudFrontUtilities cloudFrontUtilities() {
		return CloudFrontUtilities.create();
	}
}
