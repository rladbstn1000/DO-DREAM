package A704.DODREAM.indexing;

import java.nio.charset.StandardCharsets;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class IndexingSourceTests {
    @Test void publishedSnapshotHasOneStableStringOnlyCanonicalForm() {
        var source=new LinkedHashMap<String,Object>();
        source.put("teacher_notes",Map.of("answer","SECRET"));
        source.put("chapters",List.of(Map.of("type","content","content","한글 😀\nline","answer","SECRET"),
            Map.of("type","quiz","qa",List.of(Map.of("question","q","answer","SECRET")))));
        var snapshot=IndexingSource.material(source);
        String expected="{\"blocks\":[{\"text\":\"한글 😀\\nline\",\"type\":\"content\"}]}";
        assertEquals(expected,snapshot.json());
        assertEquals(expected.getBytes(StandardCharsets.UTF_8).length,snapshot.bytes());
        assertEquals(IndexingSource.hash(expected.getBytes(StandardCharsets.UTF_8)),snapshot.hash());
        assertFalse(snapshot.json().contains("SECRET"));
    }
    @Test void metadataAndMapOrderDoNotChangeContentHash() {
        var a=IndexingSource.material(Map.of("chapters",List.of(Map.of("content"," text ","type","content","title","a"))));
        var b=IndexingSource.material(Map.of("chapters",List.of(Map.of("type","content","title","b","content"," text "))));
        assertEquals(a,b);
        assertNotEquals(a.hash(),IndexingSource.material(Map.of("chapters",List.of(Map.of("type","content","content","text")))).hash());
    }
    @Test void initialLegacyContentsAreIncludedInOrderButConceptAnswersAreExcluded() throws Exception {
        var initial=IndexingSource.JSON.readTree("""
            {"parsedData":{"data":[{"titles":[
              {"title":"개념 CHECK","s_titles":[{"contents":"SECRET"}]},
              {"title":"큰 제목","s_titles":[{"s_title":"중간 제목","contents":"본문", "ss_titles":[{"ss_title":"작은 제목","contents":"두번째"}]}]}]}]}}
            """);
        var snapshot=IndexingSource.initial(initial);
        assertEquals("{\"blocks\":[{\"text\":\"큰 제목\\n중간 제목\\n본문\",\"type\":\"content\"},{\"text\":\"큰 제목\\n중간 제목\\n작은 제목\\n두번째\",\"type\":\"content\"}]}",snapshot.json());
        assertFalse(snapshot.json().contains("SECRET"));
    }
    @Test void emptyAndPlaceholderAreExplicitFailures() {
        for(String text:List.of("", " \n\t", "\u0085\u00a0", "[새 챕터의 내용을 입력하세요]", "새 챕터의 내용을 입력하세요")) {
            assertEquals(422,assertThrows(IndexingFailure.class,()->IndexingSource.material(Map.of("chapters",List.of(Map.of("type","content","content",text))))).status());
        }
    }
    @Test void initialConceptAnswersAtEveryHeadingDepthAreExcluded() throws Exception {
        var parsed=IndexingSource.JSON.readTree("""
            {"data":[{"titles":[{"title":"본문","s_titles":[
              {"s_title":"개념 Check","contents":"SUB_SECRET","ss_titles":[{"contents":"SUB_NESTED_SECRET"}]},
              {"s_title":"학습","contents":"safe","ss_titles":[
                {"ss_title":"개념 CHECK","contents":"NESTED_SECRET"},{"ss_title":"설명","contents":"safe two"}]}]}]}]}
            """);
        var snapshot=IndexingSource.initial(parsed);
        assertFalse(snapshot.json().contains("SECRET"));
        assertTrue(snapshot.json().contains("safe two"));
    }
    @Test void malformedUnicodeControlCharactersAndNonStringBodiesAreRejected() {
        for(String text:List.of("\ud800", "\udc00", "abc\u0000", "\b"))
            assertThrows(IndexingFailure.class,()->IndexingSource.snapshot(List.of(text)));
        assertThrows(IndexingFailure.class,()->IndexingSource.material(Map.of("chapters",List.of(Map.of("type","content","content",12)))));
        assertThrows(IndexingFailure.class,()->IndexingSource.initial(IndexingSource.JSON.createObjectNode().put("data", "not-an-array")));
        assertThrows(IndexingFailure.class,()->IndexingSource.initial(IndexingSource.JSON.createObjectNode().put("parsedData", "not-an-object")));
        assertThrows(IndexingFailure.class,()->IndexingSource.initial(IndexingSource.JSON.createObjectNode().put("chapters", "not-an-array")));
    }
    @Test void rawJsonDuplicateTrailingAndByteLimitsAreStrict() {
        for(String text:List.of("{\"chapters\":[],\"chapters\":[]}","{} {}", "[]"))
            assertThrows(IndexingFailure.class,()->IndexingSource.parse(text.getBytes(StandardCharsets.UTF_8)));
        assertThrows(IndexingFailure.class,()->IndexingSource.snapshot(List.of("가".repeat(700000))));
        assertThrows(IndexingFailure.class,()->IndexingSource.snapshot(Collections.nCopies(501,"text")));
    }
    @Test void scopeNamesAreNotTruncatedOrSilentlyDefaulted() {
        assertEquals("local-hash8-content-v1",IndexingSource.spec(null));
        assertEquals("local-hash8-content-v2",IndexingSource.spec("local-hash8-content-v2"));
        assertThrows(IndexingFailure.class,()->IndexingSource.spec("unknown"));
        assertThrows(IndexingFailure.class,()->IndexingSource.uuid("other_00000000-0000-0000-0000-000000000001"));
    }
}
