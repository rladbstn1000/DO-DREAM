package A704.DODREAM.authorization;

import java.util.*;

/** Allowlisted learning structure. Unknown teacher metadata and answer/rubric fields never pass through. */
public final class StudentContent {
    private StudentContent() {}
    private static final Set<String> TEXT = Set.of("id", "type", "title", "c_title", "s_title", "ss_title",
        "content", "text", "question", "question_type", "question_number", "chapter_reference", "index", "index_title");
    private static final Set<String> CHILDREN = Set.of("chapters", "sections", "titles", "s_titles", "ss_titles", "qa", "data", "content");
    public static Object clean(Object source) {
        if (source instanceof Map<?, ?> map) {
            Map<String, Object> result = new LinkedHashMap<>();
            map.forEach((key, value) -> {
                if (!(key instanceof String name)) return;
                if (CHILDREN.contains(name) && (value instanceof Map || value instanceof List)) result.put(name, clean(value));
                else if (TEXT.contains(name) && (value instanceof String || value instanceof Number || value instanceof Boolean)) result.put(name, value);
            });
            return result;
        }
        if (source instanceof List<?> list) return list.stream().filter(value -> value instanceof Map).map(StudentContent::clean).toList();
        return null;
    }
    @SuppressWarnings("unchecked")
    public static Map<String, Object> document(Map<String, Object> source) { return (Map<String, Object>) clean(source); }
}
