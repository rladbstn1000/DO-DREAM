package A704.DODREAM.quiz.grading;
import org.springframework.core.annotation.Order;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import java.util.Map;
@RestControllerAdvice
@Order(org.springframework.core.Ordered.HIGHEST_PRECEDENCE)
public class GradingExceptionHandler {
    @ExceptionHandler(GradingFailure.class)
    ResponseEntity<?> grading(GradingFailure e) { return ResponseEntity.status(e.status).body(Map.of("code",e.code)); }
}
