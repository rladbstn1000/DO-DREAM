package A704.DODREAM.local;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;

class LocalObjectStoreTests {
    @TempDir java.nio.file.Path directory;
    @Test void newSyntheticObjectCanBeEditedAndReadWithoutChangingLegacyFixture() {
        var store = new LocalObjectStore(directory.toString());
        String key = "local/synthetic/authz/test-object.json";
        byte[] original = store.read(LocalExternalConfiguration.FIXTURE_KEY);
        store.write(key, "{\"chapters\":[]}".getBytes(StandardCharsets.UTF_8));
        store.write(key, "{\"chapters\":[{\"title\":\"edited\"}]}".getBytes(StandardCharsets.UTF_8));
        assertTrue(new String(store.read(key), StandardCharsets.UTF_8).contains("edited"));
        assertArrayEquals(original, store.read(LocalExternalConfiguration.FIXTURE_KEY));
        assertThrows(ResponseStatusException.class, () -> store.write(LocalExternalConfiguration.FIXTURE_KEY, "{}".getBytes()));
    }
    @Test void traversalAndOtherObjectsAreUnavailable() {
        var store = new LocalObjectStore(directory.toString());
        for (String key : java.util.List.of("../../env", "local/synthetic/authz/../env.json", "private/data.json")) {
            assertThrows(ResponseStatusException.class, () -> store.read(key));
            assertThrows(ResponseStatusException.class, () -> store.write(key, "{}".getBytes()));
        }
    }
    @Test void initializeNeverOverwritesExistingSyntheticEdits() {
        var store = new LocalObjectStore(directory.toString());
        String key = "local/synthetic/authz/preserved.json";
        store.initialize(key, "{\"value\":1}".getBytes());
        store.initialize(key, "{\"value\":2}".getBytes());
        assertTrue(new String(store.read(key), StandardCharsets.UTF_8).contains("1"));
    }
}
