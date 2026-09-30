package A704.DODREAM.indexing;

import java.util.Map;
import org.springframework.core.annotation.Order;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestControllerAdvice @Order(-1)
public class IndexingFailureHandler {
    @ExceptionHandler(IndexingFailure.class)
    public ResponseEntity<Map<String,String>> handle(IndexingFailure failure) {
        return ResponseEntity.status(failure.status()).body(Map.of("code",failure.code()));
    }
}
