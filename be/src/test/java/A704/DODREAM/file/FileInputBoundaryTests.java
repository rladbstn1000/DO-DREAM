package A704.DODREAM.file;

import A704.DODREAM.config.JsonRequestLimitFilter;
import A704.DODREAM.file.service.PdfInputPolicy;
import java.io.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.mock.web.*;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;

class FileInputBoundaryTests {
    @ParameterizedTest
    @ValueSource(strings={"../lesson.pdf", "C:\\lesson.pdf", "lesson\n.pdf", "lesson.txt", ""})
    void rejectsPathAndInvalidPdfNames(String name) {
        assertEquals(400,assertThrows(ResponseStatusException.class,()->PdfInputPolicy.filename(name)).getStatusCode().value());
    }
    @Test void acceptsUnicodePdfNameAndRequiresSignature() throws Exception {
        PdfInputPolicy.filename("물의 순환.PDF");
        assertEquals("%PDF-1.7",new String(PdfInputPolicy.read(new ByteArrayInputStream("%PDF-1.7".getBytes()),-1)));
        assertEquals(400,assertThrows(ResponseStatusException.class,()->PdfInputPolicy.content("not a PDF".getBytes())).getStatusCode().value());
        assertEquals(400,assertThrows(ResponseStatusException.class,()->PdfInputPolicy.filename("가".repeat(252)+".pdf")).getStatusCode().value());
    }
    @Test void contentLengthRejectionDoesNotConsumeBody() {
        InputStream unreadable=new InputStream() { public int read() { fail("oversized declared body was read"); return -1; } };
        assertEquals(413,assertThrows(ResponseStatusException.class,()->PdfInputPolicy.read(unreadable,PdfInputPolicy.MAX_BYTES+1)).getStatusCode().value());
    }
    @Test void missingLengthAndLyingLengthStillHaveBoundedConsumption() {
        for (long declared: new long[]{-1,5}) {
            final int[] consumed={0};
            InputStream endless=new InputStream() {
                @Override public int read() { consumed[0]++; return 'A'; }
                @Override public int read(byte[] b,int offset,int length) {
                    java.util.Arrays.fill(b,offset,offset+length,(byte)'A'); consumed[0]+=length; return length;
                }
            };
            assertEquals(413,assertThrows(ResponseStatusException.class,()->PdfInputPolicy.read(endless,declared)).getStatusCode().value());
            assertEquals(PdfInputPolicy.MAX_BYTES+1,consumed[0]);
        }
    }
    @Test void oversizedChunkedJsonNeverReachesControllerAndSmallJsonIsIntact() throws Exception {
        var oversized=new MockHttpServletRequest("POST","/api/pdf/1/temp-save") {
            @Override public long getContentLengthLong() { return -1; }
        };
        oversized.setContentType("application/json;charset=UTF-8");
        oversized.setContent(new byte[JsonRequestLimitFilter.MAX_BYTES+1]);
        var response=new MockHttpServletResponse();
        new JsonRequestLimitFilter().doFilter(oversized,response,(req,res)->fail("oversized body reached controller"));
        assertEquals(413,response.getStatus());
        var valid=new MockHttpServletRequest("POST","/api/pdf/1/temp-save");
        valid.setContentType("application/json"); valid.setContent("{\"title\":\"공개 합성 자료\"}".getBytes(java.nio.charset.StandardCharsets.UTF_8));
        new JsonRequestLimitFilter().doFilter(valid,new MockHttpServletResponse(),(req,res)->
            assertArrayEquals(valid.getContentAsByteArray(),req.getInputStream().readAllBytes()));
    }
}
