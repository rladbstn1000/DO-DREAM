package A704.DODREAM.indexing;

import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadFeature;
import com.fasterxml.jackson.databind.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

/** Versioned index input, never a mutable URL or teacher answer document. */
public final class IndexingSource {
    private IndexingSource() {}
    public static final int MAX_BYTES=2*1024*1024;
    public static final String DEFAULT_SPEC="local-hash8-content-v1";
    public static final String LIVE_SPEC="openai-text-embedding-3-small-1536-l2-content-v1";
    public static final Set<String> SPECS=Set.of(DEFAULT_SPEC,"local-hash8-content-v2",LIVE_SPEC);
    public static final ObjectMapper JSON=new ObjectMapper(JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION).build())
        .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
    public record Snapshot(String json, String hash, int bytes) {}
    public static IndexingFailure invalid() { return new IndexingFailure(400,"INVALID_INDEXING_SOURCE"); }
    public static String spec(String value) {
        String selected=value==null?DEFAULT_SPEC:value;
        if(!SPECS.contains(selected)) throw new IndexingFailure(400,"UNSUPPORTED_INDEX_SPEC");
        return selected;
    }
    public static String uuid(String value) {
        if(value==null || !value.matches("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")) throw invalid();
        return value;
    }
    public static String hash(byte[] bytes) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
        catch(java.security.NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
    public static JsonNode parse(byte[] bytes) {
        if(bytes.length==0 || bytes.length>MAX_BYTES) throw invalid();
        try {
            JsonNode parsed=JSON.readTree(bytes);
            if(!parsed.isObject()) throw invalid();
            return parsed;
        } catch(java.io.IOException failure) { throw invalid(); }
    }
    public static Snapshot material(Map<String,Object> source) { return material(JSON.<JsonNode>valueToTree(source)); }
    public static Snapshot material(JsonNode source) {
        List<String> blocks=new ArrayList<>();
        JsonNode chapters=source.path("chapters");
        if(!chapters.isArray()) throw invalid();
        for(JsonNode chapter:chapters) {
            if(!chapter.isObject()) throw invalid();
            if(!"content".equals(chapter.path("type").textValue())) continue;
            String text=string(chapter,"content");
            if(!blank(text) && !text.contains("새 챕터의 내용을 입력하세요")) blocks.add(text);
        }
        return snapshot(blocks);
    }
    public static Snapshot initial(JsonNode source) {
        // Parsed PDF and published editor content are different input formats.
        if(source.has("chapters")) return material(source);
        if(source.has("parsedData") && !source.path("parsedData").isObject()) throw invalid();
        JsonNode data=source.path("parsedData").isObject()?source.path("parsedData").path("data"):source.path("data");
        if(!data.isArray()) throw invalid();
        List<String> blocks=new ArrayList<>();
        for(JsonNode section:data) for(JsonNode title:array(section,"titles")) {
            String heading=string(title,"title");
            if(conceptCheck(heading)) continue;
            for(JsonNode sub:array(title,"s_titles")) {
                String subheading=string(sub,"s_title");
                if(conceptCheck(subheading)) continue;
                String content=string(sub,"contents");
                if(!blank(content)) blocks.add(heading+"\n"+subheading+"\n"+content);
                for(JsonNode nested:array(sub,"ss_titles")) {
                    if(conceptCheck(string(nested,"ss_title"))) continue;
                    String nestedContent=string(nested,"contents");
                    if(!blank(nestedContent)) blocks.add(heading+"\n"+subheading+"\n"+string(nested,"ss_title")+"\n"+nestedContent);
                }
            }
        }
        return snapshot(blocks);
    }
    private static boolean conceptCheck(String heading) { return heading.contains("개념") && heading.toLowerCase(Locale.ROOT).contains("check"); }
    private static Iterable<JsonNode> array(JsonNode parent,String key) {
        if(!parent.isObject()) throw invalid();
        JsonNode value=parent.path(key);
        if(value.isMissingNode() || value.isNull()) return List.of();
        if(!value.isArray()) throw invalid();
        return value;
    }
    private static String string(JsonNode parent,String key) {
        if(!parent.isObject()) throw invalid();
        JsonNode value=parent.path(key);
        if(value.isMissingNode() || value.isNull()) return "";
        if(!value.isTextual()) throw invalid();
        validate(value.textValue());
        return value.textValue();
    }
    public static void validate(String value) {
        for(int i=0;i<value.length();i++) {
            char c=value.charAt(i);
            if(c<32 && c!='\n' && c!='\r' && c!='\t') throw invalid();
            if(Character.isHighSurrogate(c)) {
                if(i+1>=value.length() || !Character.isLowSurrogate(value.charAt(++i))) throw invalid();
            } else if(Character.isLowSurrogate(c)) throw invalid();
        }
    }
    private static boolean blank(String value) {
        return value.codePoints().allMatch(c->Character.isWhitespace(c)||Character.isSpaceChar(c)||c==0x85);
    }
    public static Snapshot snapshot(List<String> texts) {
        if(texts.isEmpty() || texts.size()>500) throw new IndexingFailure(422,"EMPTY_OR_EXCESSIVE_INDEXING_CONTENT");
        var root=JSON.createObjectNode(); var blocks=root.putArray("blocks");
        for(String text:texts) { validate(text); blocks.addObject().put("text",text).put("type","content"); }
        try {
            String json=JSON.writeValueAsString(root);
            byte[] bytes=json.getBytes(StandardCharsets.UTF_8);
            if(bytes.length>MAX_BYTES) throw new IndexingFailure(413,"INDEXING_SOURCE_TOO_LARGE");
            return new Snapshot(json,hash(bytes),bytes.length);
        } catch(java.io.IOException impossible) { throw new IllegalStateException(impossible); }
    }
}
