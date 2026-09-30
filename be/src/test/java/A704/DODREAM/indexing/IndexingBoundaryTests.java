package A704.DODREAM.indexing;

import A704.DODREAM.authorization.*;
import A704.DODREAM.material.dto.PublishRequest;
import A704.DODREAM.local.LocalObjectStore;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import software.amazon.awssdk.services.s3.S3Client;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class IndexingBoundaryTests {
    @TempDir java.nio.file.Path directory;
    @Test void permissionDenialPrecedesObjectWriteAndLedger() {
        var store=mock(IndexingStore.class); var objects=mock(S3Client.class); var hooks=mock(IndexingLocalHooks.class);
        var service=new IndexingService(store,objects,hooks,"local-synthetic-fixtures");
        var request=new PublishRequest();
        when(store.prepareFile(21,73,request)).thenThrow(AuthorizationPolicy.hidden());
        assertThrows(AuthorizationFailure.class,()->service.publish(21,73,request));
        verifyNoInteractions(objects,hooks);
        verify(store,never()).publish(anyLong(),anyLong(),any(),any(),any(),any());
    }
    @Test void emptySourcePrecedesAllStorageAndPublication() {
        var store=mock(IndexingStore.class); var objects=mock(S3Client.class); var hooks=mock(IndexingLocalHooks.class);
        var service=new IndexingService(store,objects,hooks,"local-synthetic-fixtures");
        var request=PublishRequest.builder().materialTitle("test").editedJson(Map.of("chapters",List.of())).build();
        when(store.prepareFile(21,73,request)).thenReturn(new IndexingStore.FileView(73,21,"name","source","key","bucket",null,false));
        assertEquals(422,assertThrows(IndexingFailure.class,()->service.publish(21,73,request)).status());
        verifyNoInteractions(objects,hooks);
        verify(store,never()).publish(anyLong(),anyLong(),any(),any(),any(),any());
    }
    @Test void newIndexObjectsAreImmutableWhileLegacyFixtureRemainsUnchanged() {
        var objects=new LocalObjectStore(directory.toString());
        String key="local/synthetic/indexing/"+UUID.randomUUID()+".json";
        byte[] first="{\"value\":1}".getBytes(StandardCharsets.UTF_8);
        objects.write(key,first);
        assertThrows(org.springframework.web.server.ResponseStatusException.class,()->objects.write(key,"{\"value\":2}".getBytes()));
        assertArrayEquals(first,objects.read(key));
    }
    @Test void syntheticPdfObjectsRequireKnownPrefixAndPdfMagicAndAreImmutable() {
        var objects=new LocalObjectStore(directory.toString());
        String key="local/synthetic/indexing-pdf/"+UUID.randomUUID()+".pdf";
        assertThrows(org.springframework.web.server.ResponseStatusException.class,()->objects.write(key,"not a PDF".getBytes()));
        byte[] pdf="%PDF-1.7\nDO-DREAM LOCAL SYNTHETIC FIXTURE".getBytes(StandardCharsets.US_ASCII);
        objects.write(key,pdf); assertArrayEquals(pdf,objects.read(key));
        assertThrows(org.springframework.web.server.ResponseStatusException.class,()->objects.write(key,pdf));
        assertThrows(org.springframework.web.server.ResponseStatusException.class,()->objects.write("pdfs/foreign.pdf",pdf));
    }
}
