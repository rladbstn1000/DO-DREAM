package A704.DODREAM.authorization;

import java.util.Map;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class AuthorizationFailureHandler {
    @ExceptionHandler(AuthorizationFailure.class)
    public ResponseEntity<Map<String, String>> handle(AuthorizationFailure exception) {
        return ResponseEntity.status(exception.getStatus()).body(Map.of("code", "RESOURCE_ACCESS_DENIED"));
    }
    @ExceptionHandler(org.springframework.web.server.ResponseStatusException.class)
    public ResponseEntity<Map<String, String>> boundary(org.springframework.web.server.ResponseStatusException exception) {
        return ResponseEntity.status(exception.getStatusCode()).body(Map.of("code", "PROVIDER_UNAVAILABLE"));
    }
    @ExceptionHandler({org.springframework.web.method.annotation.MethodArgumentTypeMismatchException.class,
        org.springframework.http.converter.HttpMessageNotReadableException.class,
        org.springframework.web.bind.MissingServletRequestParameterException.class})
    public ResponseEntity<Map<String, String>> invalidRequest(Exception exception) {
        return ResponseEntity.badRequest().body(Map.of("code", "INVALID_REQUEST"));
    }
}
