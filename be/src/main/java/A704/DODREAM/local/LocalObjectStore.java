package A704.DODREAM.local;

import java.nio.file.*;
import java.security.MessageDigest;
import java.util.HexFormat;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

/** Synthetic object bytes only. No network client and no path derived directly from an object key. */
@Component
@Profile("local")
public class LocalObjectStore {
    private final Path directory;
    public LocalObjectStore(@Value("${local.object-storage-dir:/app/local-data/objects}") String directory) {
        this.directory = Path.of(directory);
    }
    public static boolean writable(String key) {
        return key != null && (key.matches("local/synthetic/authz/[a-z0-9-]+\\.json")
            || key.matches("local/synthetic/indexing/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\\.json")
            || key.matches("local/synthetic/indexing-pdf/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\\.pdf"));
    }
    public static String hash(String key) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(key.getBytes(java.nio.charset.StandardCharsets.UTF_8))); }
        catch (java.security.NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
    public byte[] read(String key) {
        if (LocalExternalConfiguration.FIXTURE_KEY.equals(key)) return LocalExternalConfiguration.fixture(key);
        if (!writable(key)) throw unavailable();
        try { return Files.readAllBytes(path(key)); }
        catch (java.io.IOException failure) { throw unavailable(); }
    }
    public synchronized void write(String key, byte[] bytes) {
        if (!writable(key) || bytes.length > 2 * 1024 * 1024) throw unavailable();
        try {
            if(key.startsWith("local/synthetic/indexing-pdf/")) {
                if(bytes.length<8 || !new String(bytes,0,5,java.nio.charset.StandardCharsets.US_ASCII).equals("%PDF-")) throw unavailable();
            } else new com.fasterxml.jackson.databind.ObjectMapper().readTree(bytes);
            Files.createDirectories(directory);
            Path target = path(key);
            if(key.startsWith("local/synthetic/indexing/") || key.startsWith("local/synthetic/indexing-pdf/")) {
                // Newly prepared objects are append-only. Publication only changes its DB reference.
                Files.write(target,bytes,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE);
                return;
            }
            Path temporary = Files.createTempFile(directory, ".write-", ".json");
            try { Files.write(temporary, bytes); Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING); }
            finally { Files.deleteIfExists(temporary); }
        } catch (java.io.IOException failure) { throw unavailable(); }
    }
    public void initialize(String key, byte[] bytes) {
        if (!writable(key)) throw unavailable();
        if (!Files.exists(path(key))) write(key, bytes);
    }
    private Path path(String key) { return directory.resolve(hash(key)+(key.endsWith(".pdf")?".pdf":".json")); }
    public static org.springframework.web.server.ResponseStatusException unavailable() {
        return new org.springframework.web.server.ResponseStatusException(org.springframework.http.HttpStatus.SERVICE_UNAVAILABLE,
            "LOCAL_EXTERNAL_DISABLED: Only named synthetic objects are supported");
    }
}
