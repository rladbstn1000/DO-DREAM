package A704.DODREAM.file;

import A704.DODREAM.auth.dto.request.UserPrincipal;
import A704.DODREAM.authorization.AuthorizationFailure;
import A704.DODREAM.authorization.AuthorizationPolicy;
import A704.DODREAM.file.controller.PdfController;
import A704.DODREAM.file.service.PdfInputPolicy;
import A704.DODREAM.file.service.PdfService;
import A704.DODREAM.indexing.IndexingLocalHooks;
import A704.DODREAM.indexing.IndexingStore;
import jakarta.servlet.ServletInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

/** Caller regression: permission keeps preceding body reads and uses the bounded store path. */
class PdfUploadPermissionBoundaryTests {
    final IndexingStore store=mock(IndexingStore.class);
    final PdfService service=mock(PdfService.class);
    final AuthorizationPolicy policy=mock(AuthorizationPolicy.class);
    final UserPrincipal principal=new UserPrincipal(21L,"synthetic","TEACHER");

    PdfController controller() {
        var controller=new PdfController();
        ReflectionTestUtils.setField(controller,"indexingStore",store);
        ReflectionTestUtils.setField(controller,"indexingHooks",mock(IndexingLocalHooks.class));
        ReflectionTestUtils.setField(controller,"pdfService",service);
        ReflectionTestUtils.setField(controller,"policy",policy);
        return controller;
    }
    @Test void boundedPermissionCompletesBeforeBodyReadAndExistingServiceValidationRemains() throws Exception {
        var authorized=new AtomicBoolean();
        var request=new MockHttpServletRequest() {
            @Override public ServletInputStream getInputStream() {
                assertTrue(authorized.get(),"Request body must not be read before bounded permission finishes");
                return super.getInputStream();
            }
        };
        byte[] body="%PDF-1.7\nsynthetic".getBytes(StandardCharsets.US_ASCII);
        request.setContent(body);
        doAnswer(call->{authorized.set(true);return null;}).when(store).teacher(21L);
        when(service.uploadAndParsePdfFromBytes(body,"synthetic.pdf",21L,null)).thenReturn(Map.of("pdfId",73L));
        assertEquals(200,controller().uploadAndParsePdfBinary("synthetic.pdf",principal,request).getStatusCode().value());
        verify(store).teacher(21L);
        verify(policy,never()).teacher(anyLong());
        verify(service).uploadAndParsePdfFromBytes(body,"synthetic.pdf",21L,null);
    }
    @Test void deniedPermissionNeverReadsInputOrCallsPdfService() {
        var request=new MockHttpServletRequest() {
            @Override public ServletInputStream getInputStream() { fail("Denied request body was read"); return null; }
        };
        doThrow(AuthorizationPolicy.hidden()).when(store).teacher(21L);
        assertThrows(AuthorizationFailure.class,()->controller().uploadAndParsePdfBinary("synthetic.pdf",principal,request));
        verifyNoInteractions(service,policy);
    }
    @Test void invalidPdfAndOversizedInputStillFailBeforeServiceWork() throws IOException {
        var malformed=new MockHttpServletRequest();
        malformed.setContent("not a PDF".getBytes(StandardCharsets.US_ASCII));
        assertEquals(400,assertThrows(ResponseStatusException.class,
            ()->controller().uploadAndParsePdfBinary("synthetic.pdf",principal,malformed)).getStatusCode().value());
        var oversized=new MockHttpServletRequest() {
            @Override public long getContentLengthLong() { return PdfInputPolicy.MAX_BYTES+1L; }
            @Override public ServletInputStream getInputStream() {
                return new org.springframework.mock.web.DelegatingServletInputStream(new java.io.InputStream() {
                    @Override public int read() { fail("Oversized declared body was read"); return -1; }
                });
            }
        };
        assertEquals(413,assertThrows(ResponseStatusException.class,
            ()->controller().uploadAndParsePdfBinary("synthetic.pdf",principal,oversized)).getStatusCode().value());
        verify(store,times(2)).teacher(21L);
        verifyNoInteractions(service,policy);
    }
}
