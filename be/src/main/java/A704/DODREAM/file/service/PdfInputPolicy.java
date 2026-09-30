package A704.DODREAM.file.service;

import java.io.IOException;
import java.io.InputStream;
import java.util.Locale;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

/** Shared limits for binary HTTP uploads and service callers, before storage/provider work. */
public final class PdfInputPolicy {
    public static final int MAX_BYTES = 10 * 1024 * 1024;
    private PdfInputPolicy() {}

    public static void filename(String name) {
        if (name == null || name.isBlank() || name.length() > 255 || name.contains("/") || name.contains("\\")
            || name.codePoints().anyMatch(Character::isISOControl) || !name.toLowerCase(Locale.ROOT).endsWith(".pdf")) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "INVALID_PDF_FILENAME");
        }
    }

    public static byte[] read(InputStream input, long contentLength) throws IOException {
        if (contentLength > MAX_BYTES) throw tooLarge();
        byte[] bytes = input.readNBytes(MAX_BYTES + 1);
        content(bytes);
        return bytes;
    }

    public static void content(byte[] bytes) {
        if (bytes != null && bytes.length > MAX_BYTES) throw tooLarge();
        // A PDF signature is an input format check, not a guarantee that the document is safe to parse.
        if (bytes == null || bytes.length < 5 || bytes[0] != '%' || bytes[1] != 'P' || bytes[2] != 'D'
            || bytes[3] != 'F' || bytes[4] != '-') {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "INVALID_PDF_CONTENT");
        }
    }

    private static ResponseStatusException tooLarge() {
        return new ResponseStatusException(HttpStatus.PAYLOAD_TOO_LARGE, "PDF_TOO_LARGE");
    }
}
