package A704.DODREAM.demo;

import A704.DODREAM.indexing.IndexingSource;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class Phase5ManifestTests {
    @Test void exactlyFourSeparateAuthoredCopiesAndTwentyServerQuizzes() {
        assertEquals(4,Phase5Manifest.SAMPLES.size());
        assertEquals(20,Phase5Manifest.SAMPLES.stream().mapToInt(s->s.questions().size()).sum());
        assertEquals(4,Phase5Manifest.SAMPLES.stream().map(Phase5Manifest.Sample::sampleKey).distinct().count());
        assertTrue(Phase5Manifest.RESOURCE_SHA256.matches("[a-f0-9]{64}"));
        for(var sample:Phase5Manifest.SAMPLES) {
            assertTrue(sample.sampleKey().startsWith("phase5eval-"));
            assertTrue(DemoManifest.SAMPLES.stream().noneMatch(old->old.key().equals(sample.sampleKey())));
            assertEquals(sample.sourceHash(),IndexingSource.material(sample.document()).hash());
            assertEquals(sample.sourceHash(),IndexingSource.initial(IndexingSource.JSON.valueToTree(sample.initial())).hash());
            assertEquals(sample.questions().size(),sample.publication().getQuizzes().size());
        }
    }
    @Test void AllSixteenCasesHaveStableMappingAndNoGoldInLearningSource() throws Exception {
        Set<String> ids=new HashSet<>();
        for(var sample:Phase5Manifest.SAMPLES) {
            var source=IndexingSource.material(sample.document()).json();
            var fields=IndexingSource.JSON.readTree(source).get("blocks");
            for(var block:fields) {
                var names=new HashSet<String>();block.fieldNames().forEachRemaining(names::add);
                assertEquals(Set.of("text","type"),names);
                assertEquals("content",block.get("type").asText());
            }
            for(var q:sample.questions())if(!q.caseId().isBlank())assertTrue(ids.add(q.caseId()));
            assertFalse(source.contains("correct_answer"));assertFalse(source.contains("evaluation_case_id"));
            assertFalse(source.contains("expected_is_correct"));
        }
        assertEquals(16,ids.size());assertTrue(ids.containsAll(List.of("G01","G08","G09","G16")));
    }
}
