package A704.DODREAM.file;

import A704.DODREAM.file.service.*;
import A704.DODREAM.file.dto.PresignedUrlRequest;
import A704.DODREAM.file.repository.UploadedFileRepository;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.web.server.ResponseStatusException;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class ObjectAndPathBoundaryTests {
    @TempDir Path directory;
    @Test void ownedPathsRejectTraversalAndSymlinksAndKeepOtherFilesIntact() throws Exception {
        var storage=new FileStorageService(directory.resolve("upload").toString(),directory.resolve("temp").toString());
        Path outside=directory.resolve("outside.pdf"); Files.writeString(outside,"preserve");
        for(String name:List.of("../outside.pdf",outside.toString(),"..\\outside.pdf")) {
            assertThrows(IllegalArgumentException.class,()->storage.getFilePath(name));
            assertThrows(IllegalArgumentException.class,()->storage.deleteFile(name));
        }
        Files.createSymbolicLink(directory.resolve("upload/link.pdf"),outside);
        assertThrows(IllegalArgumentException.class,()->storage.getFilePath("link.pdf"));
        assertThrows(IllegalArgumentException.class,()->storage.deleteTempFile(outside.toFile()));
        assertThrows(IllegalArgumentException.class,()->storage.saveTempFile(new byte[]{1},"../outside","png"));
        assertEquals("preserve",Files.readString(outside));
        var valid=new MockMultipartFile("file","합성.pdf","application/pdf","%PDF-1.7".getBytes());
        String stored=storage.storeFile(valid);
        assertTrue(storage.getFilePath(stored).startsWith(directory.resolve("upload")));
        assertArrayEquals(valid.getBytes(),Files.readAllBytes(storage.getFilePath(stored)));
    }
    @Test void storedJsonReadsBoundedUtf8AndAlwaysReleasesOrAbortsTheStream() throws Exception {
        List<String> events=new ArrayList<>();
        byte[] text="{\"title\":\"합성\"}".getBytes(java.nio.charset.StandardCharsets.UTF_8);
        assertEquals("{\"title\":\"합성\"}",ObjectJsonReader.read(response(text,events,text.length)));
        assertEquals(List.of("close"),events);
        for (long length:new long[]{1,ObjectJsonReader.MAX_BYTES+1}) {
            events.clear();
            assertThrows(IOException.class,()->ObjectJsonReader.read(response(new byte[ObjectJsonReader.MAX_BYTES+1],events,length)));
            assertEquals("abort",events.get(0)); assertTrue(events.contains("close"));
        }
    }
    @Test void presignedUploadRejectsMissingOrUnboundedSizeBeforeDatabaseOrSigning() {
        var signer=mock(S3Presigner.class); var files=mock(UploadedFileRepository.class);
        var service=new S3Service(signer,files);
        for(Long size:Arrays.asList(null,0L,-1L,(long)PdfInputPolicy.MAX_BYTES+1))
            assertEquals(400,assertThrows(ResponseStatusException.class,
                ()->service.generatePresignedUrl(new PresignedUrlRequest("synthetic.pdf","application/pdf",size),1L)).getStatusCode().value());
        verifyNoInteractions(signer,files);
    }
    private ResponseInputStream<GetObjectResponse> response(byte[] bytes,List<String> events,long length) {
        var stream=new ByteArrayInputStream(bytes) {
            @Override public void close() throws IOException { events.add("close"); super.close(); }
        };
        var abortable=software.amazon.awssdk.http.AbortableInputStream.create(stream,() -> events.add("abort"));
        return new ResponseInputStream<>(GetObjectResponse.builder().contentLength(length).build(),abortable);
    }
}
