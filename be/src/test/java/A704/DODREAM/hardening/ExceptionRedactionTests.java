package A704.DODREAM.hardening;

import A704.DODREAM.global.exception.handlers.GlobalExceptionHandler;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;

class ExceptionRedactionTests {
    @Test void providerFailureCannotPlacePayloadOrUrlInPublicResponseOrLog() {
        String sentinel="synthetic-secret-must-not-be-logged";
        var logger=(Logger)LoggerFactory.getLogger(GlobalExceptionHandler.class);
        var appender=new ListAppender<ch.qos.logback.classic.spi.ILoggingEvent>();
        appender.start(); logger.addAppender(appender);
        try {
            var request=new MockHttpServletRequest("GET","/api/pdf/"+sentinel);
            var result=new GlobalExceptionHandler().handleException(new RuntimeException(sentinel),request);
            assertEquals(500,result.getStatusCode().value());
            assertNotNull(result.getHeaders().getFirst("X-Error-Id"));
            assertFalse(result.toString().contains(sentinel));
            assertFalse(appender.list.isEmpty());
            for(var event:appender.list) {
                assertFalse(event.getFormattedMessage().contains(sentinel)); assertNull(event.getThrowableProxy());
            }
        } finally { logger.detachAppender(appender); }
    }
    @Test void explicitBoundaryStatusIsRetainedWithoutPublishingItsReason() {
        var result=new GlobalExceptionHandler().handleStatus(new ResponseStatusException(HttpStatus.PAYLOAD_TOO_LARGE,"synthetic-private-reason"));
        assertEquals(413,result.getStatusCode().value());
        assertFalse(result.toString().contains("synthetic-private-reason"));
    }
}
