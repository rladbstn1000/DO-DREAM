package A704.DODREAM.auth.exception;

import org.springframework.http.HttpStatus;

public class AuthException extends RuntimeException {
    private final HttpStatus status;
    private final String code;
    public AuthException(HttpStatus status, String code, String message) {
        super(message);
        this.status = status;
        this.code = code;
    }
    public HttpStatus status() { return status; }
    public String code() { return code; }
    public static AuthException unauthorized() {
        return new AuthException(HttpStatus.UNAUTHORIZED, "INVALID_AUTHENTICATION", "Authentication required");
    }
    public static AuthException unavailable() {
        return new AuthException(HttpStatus.SERVICE_UNAVAILABLE, "AUTH_STORE_UNAVAILABLE", "Authentication storage is temporarily unavailable");
    }
}
