package A704.DODREAM.file.service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;

/** Persisted object metadata is not a promise about body size; always bound actual consumption. */
public final class ObjectJsonReader {
    public static final int MAX_BYTES = 2 * 1024 * 1024;
    private ObjectJsonReader() {}
    public static String read(ResponseInputStream<GetObjectResponse> response) throws IOException {
        try (response) {
          try {
            Long length=response.response().contentLength();
            if (length != null && length > MAX_BYTES) throw new IOException("Stored JSON exceeds the size limit");
            byte[] bytes=response.readNBytes(MAX_BYTES+1);
            if (bytes.length > MAX_BYTES) throw new IOException("Stored JSON exceeds the size limit");
            return new String(bytes,StandardCharsets.UTF_8);
          } catch (IOException failure) {
            // Abort oversized/failed HTTP bodies rather than draining the rest into the connection pool.
            response.abort();
            throw failure;
          }
        }
    }
}
