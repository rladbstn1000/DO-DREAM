package A704.DODREAM.authorization;

import lombok.Getter;
import org.springframework.http.HttpStatus;

@Getter
public final class AuthorizationFailure extends RuntimeException {
    private final HttpStatus status;
    public AuthorizationFailure(HttpStatus status) {
        super("Request is not permitted");
        this.status = status;
    }
}
