package A704.DODREAM.demo;

import A704.DODREAM.authorization.StudentContent;
import A704.DODREAM.indexing.IndexingSource;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class DemoManifestTests {
    @Test void twoIndependentAuthoredSourcesHaveThreeSectionsAndTwoVersionedQuizQuestions() {
        assertEquals(2,DemoManifest.SAMPLES.size());
        for(var sample:DemoManifest.SAMPLES) {
            assertEquals(3,sample.sections().size());assertEquals(2,sample.publication().getQuizzes().size());
            assertTrue(sample.document().get("source").toString().contains("직접 작성"));
            var projected=StudentContent.document(sample.document());
            assertEquals(3,((java.util.List<?>)projected.get("chapters")).size());
            assertFalse(projected.containsKey("questions"));
            assertFalse(sample.document().toString().contains("correct_answer"));
            assertFalse(sample.document().toString().contains("qa="));
            assertTrue(IndexingSource.material(sample.document()).bytes()>0);
            assertTrue(IndexingSource.initial(IndexingSource.JSON.valueToTree(sample.initial())).bytes()>0);
        }
        assertNotEquals(IndexingSource.material(DemoManifest.SAMPLES.get(0).document()).hash(),IndexingSource.material(DemoManifest.SAMPLES.get(1).document()).hash());
    }
    @Test void manifestIsStableAndQuestionsUseOnlyItsOwnSectionReferences() {
        for(var sample:DemoManifest.SAMPLES) {
            assertEquals(IndexingSource.material(sample.document()).hash(),IndexingSource.material(sample.document()).hash());
            for(var quiz:sample.publication().getQuizzes()) {
                assertTrue(sample.sections().stream().anyMatch(s->s.id().equals(quiz.getChapterReference())));
                assertFalse(quiz.getCorrectAnswer().isBlank());
            }
        }
    }
}
