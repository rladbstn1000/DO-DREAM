package A704.DODREAM.quiz.grading;

import A704.DODREAM.quiz.dto.GradingResultDto;
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadFeature;
import com.fasterxml.jackson.databind.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.LocalDateTime;
import java.util.*;

public final class GradingContract {
    private GradingContract() {}
    public static final String UUID_PATTERN = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
    public static final ObjectMapper JSON = new ObjectMapper(JsonFactory.builder().enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION).build());
    public record Answer(long quizId, long version, String answer) {}
    public record Submission(String key, String fingerprint, List<Answer> answers) {}
    public record Attempt(long id, String attemptId, long studentId, long materialId, String key,
        String fingerprint, String state, int generation, LocalDateTime deadline, LocalDateTime dispatched,
        LocalDateTime created, String failureCode) {}
    public record Item(long quizId, long version, int number, String type, String title, String content,
        String correctAnswer, String answer, String gradingVersion) {}
    public record Result(long quizId, boolean correct, String feedback) {}
    public record Execution(Attempt attempt, String capability, List<Item> items) {}
    public record View(Attempt attempt, List<GradingResultDto> results) {}
    public record Retry(Integer expectedGeneration, Boolean confirmUnknown) {}
    public static Submission parse(String key, long materialId, JsonNode body) {
        uuid(key);
        if (body == null || !body.isObject() || !body.has("answers") || !body.get("answers").isArray()) throw error(400,"INVALID_SUBMISSION");
        JsonNode list = body.get("answers");
        if(list.isEmpty() || list.size()>50) throw error(400,"INVALID_SUBMISSION");
        TreeMap<Long, Answer> sorted=new TreeMap<>();
        for(JsonNode a:list) {
            if(!a.isObject() || !integer(a.get("quizId")) || !integer(a.get("version")) || !text(a.get("answer"),2000)) throw error(400,"INVALID_SUBMISSION");
            long id=a.get("quizId").longValue(), version=a.get("version").longValue();
            if(id<=0 || version<0 || sorted.putIfAbsent(id,new Answer(id,version,a.get("answer").textValue()))!=null) throw error(400,"INVALID_SUBMISSION");
        }
        try {
            var canonical=JSON.createObjectNode().put("materialId",materialId);
            var answers=canonical.putArray("answers");
            for(Answer a:sorted.values()) answers.addObject().put("quizId",a.quizId()).put("version",a.version()).put("answer",a.answer());
            return new Submission(key,hash(JSON.writeValueAsString(canonical)),List.copyOf(sorted.values()));
        }
        catch(Exception e) { throw error(400,"INVALID_SUBMISSION"); }
    }
    public static Retry retry(JsonNode body) {
        if(body==null || !body.isObject() || body.size()!=2 || !integer(body.get("expectedGeneration")) || body.get("expectedGeneration").longValue()<0 || body.get("expectedGeneration").longValue()>3 || body.get("confirmUnknown")==null || !body.get("confirmUnknown").isBoolean()) throw error(400,"INVALID_RECOVERY");
        return new Retry(body.get("expectedGeneration").intValue(),body.get("confirmUnknown").booleanValue());
    }
    public static List<Result> provider(String raw, List<Item> items) {
        try {
            if(raw==null || raw.length()>2*1024*1024) throw new IllegalArgumentException();
            JsonNode root=JSON.reader().with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS).readTree(raw);
            if(!root.isArray() || root.size()!=items.size()) throw new IllegalArgumentException();
            Map<Long,Item> expected=new HashMap<>(); items.forEach(i->expected.put(i.quizId(),i));
            List<Result> results=new ArrayList<>();
            for(JsonNode r:root) {
                if(!r.isObject() || r.size()!=4 || !integer(r.get("question_id")) || !text(r.get("student_answer"),2000) || !text(r.get("ai_feedback"),2000) || r.get("is_correct")==null || !r.get("is_correct").isBoolean()) throw new IllegalArgumentException();
                long id=r.get("question_id").longValue(); Item item=expected.remove(id);
                if(item==null || !item.answer().equals(r.get("student_answer").textValue())) throw new IllegalArgumentException();
                results.add(new Result(id,r.get("is_correct").booleanValue(),r.get("ai_feedback").textValue()));
            }
            if(!expected.isEmpty()) throw new IllegalArgumentException();
            return List.copyOf(results);
        } catch(Exception e) { throw error(502,"INVALID_PROVIDER_RESPONSE"); }
    }
    static boolean integer(JsonNode n) { return n!=null && n.isIntegralNumber() && n.canConvertToLong(); }
    static boolean text(JsonNode n,int max) { return n!=null && n.isTextual() && validUnicode(n.textValue()) && n.textValue().codePointCount(0,n.textValue().length())<=max; }
    private static boolean validUnicode(String value) {
        for(int i=0;i<value.length();i++) {
            char c=value.charAt(i);
            if(Character.isHighSurrogate(c)) {
                if(++i>=value.length() || !Character.isLowSurrogate(value.charAt(i))) return false;
            } else if(Character.isLowSurrogate(c)) return false;
        }
        return true;
    }
    public static void uuid(String value) { if(value==null || !value.matches(UUID_PATTERN)) throw error(400,"INVALID_IDEMPOTENCY_KEY"); }
    public static String hash(String s) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(s.getBytes(StandardCharsets.UTF_8))); }
        catch(Exception e) { throw new IllegalStateException("Digest unavailable"); }
    }
    public static GradingFailure error(int status,String code) { return new GradingFailure(status,code); }
}
