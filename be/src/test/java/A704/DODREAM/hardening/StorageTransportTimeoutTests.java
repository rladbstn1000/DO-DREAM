package A704.DODREAM.hardening;

import A704.DODREAM.config.AWSConfig;
import java.net.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import software.amazon.awssdk.http.*;
import static org.junit.jupiter.api.Assertions.*;

/** Actual locked SDK HTTP transport against only a controlled loopback socket; no AWS request/key. */
class StorageTransportTimeoutTests {
    @Test @Timeout(12)
    void stalledBodyReadUsesExplicitSocketTimeout() throws Exception {
        try (var server=new ServerSocket(0,1,InetAddress.getLoopbackAddress());
             var client=new AWSConfig().storageHttpClient()) {
            var release=new CountDownLatch(1);
            var accepted=new CompletableFuture<Socket>();
            var thread=new Thread(() -> {
                try (var socket=server.accept()) {
                    accepted.complete(socket);
                    var input=new java.io.BufferedReader(new java.io.InputStreamReader(socket.getInputStream()));
                    String line; while((line=input.readLine())!=null && !line.isEmpty()) { }
                    socket.getOutputStream().write("HTTP/1.1 200 OK\r\nContent-Length: 100\r\nConnection: close\r\n\r\nx".getBytes(java.nio.charset.StandardCharsets.US_ASCII));
                    socket.getOutputStream().flush();
                    release.await(10,TimeUnit.SECONDS);
                } catch (Exception error) { accepted.completeExceptionally(error); }
            },"hardening-loopback-storage");
            thread.setDaemon(true); thread.start();
            try {
                var request=SdkHttpFullRequest.builder().method(SdkHttpMethod.GET)
                    .uri(URI.create("http://127.0.0.1:"+server.getLocalPort()+"/synthetic")).build();
                long start=System.nanoTime();
                var result=client.prepareRequest(HttpExecuteRequest.builder().request(request).build()).call();
                var body=result.responseBody().orElseThrow();
                try {
                    assertThrows(java.io.IOException.class,body::readAllBytes);
                    long elapsedMs=TimeUnit.NANOSECONDS.toMillis(System.nanoTime()-start);
                    assertTrue(elapsedMs >= 4000 && elapsedMs < 9000,"Expected configured 5-second idle-read timeout: "+elapsedMs);
                } finally { body.abort(); body.close(); }
            } finally { release.countDown(); thread.join(1500); }
        }
    }
}
