package A704.DODREAM.config;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;

@Configuration
@Profile("!local")
public class WebClientConfig {

	@Bean
	public WebClient webClient() {
		HttpClient httpClient = HttpClient.create().disableRetry(true).followRedirect(false)
            .option(io.netty.channel.ChannelOption.CONNECT_TIMEOUT_MILLIS,2000)
            .responseTimeout(Duration.ofSeconds(5));

		return WebClient.builder()
			.clientConnector(new ReactorClientHttpConnector(httpClient))
            .codecs(codecs -> codecs.defaultCodecs().maxInMemorySize(A704.DODREAM.file.service.PdfInputPolicy.MAX_BYTES))
			.build();
	}

	@Bean
	public WebClient branchWebClient() {
		return webClient().mutate()
			.baseUrl("https://api2.branch.io")
			.defaultHeader("Content-Type", "application/json")
			.build();
	}
}