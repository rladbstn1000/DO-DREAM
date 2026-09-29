package A704.DODREAM.authorization;

import A704.DODREAM.local.LocalAuthorizationFixtures;
import A704.DODREAM.quiz.dto.StudentQuizDto;
import A704.DODREAM.quiz.entity.Quiz;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class StudentProjectionTests {
    private final ObjectMapper mapper = new ObjectMapper();
    @Test void nestedTeacherAnswersAreNotLearningContent() throws Exception {
        var source = mapper.readValue(LocalAuthorizationFixtures.BODY, Map.class);
        String output = mapper.writeValueAsString(StudentContent.document(source));
        assertFalse(output.contains("AUTHZ_TEACHER_ONLY"));
        assertFalse(output.contains("answer"));
        assertFalse(output.contains("rubric"));
        assertTrue(output.contains("question"));
        assertTrue(output.contains("authz-content"));
        assertTrue(mapper.writeValueAsString(source).contains("AUTHZ_TEACHER_ONLY"));
    }
    @Test void studentQuizDtoNeverSerializesTeacherAnswer() throws Exception {
        Quiz quiz = Quiz.builder().id(71L).questionNumber(1).questionType("SHORT_ANSWER")
            .title("Question").content("Synthetic question").correctAnswer("PRIVATE_ANSWER").build();
        Map<?, ?> result = mapper.readValue(mapper.writeValueAsString(StudentQuizDto.from(quiz)), Map.class);
        assertEquals(java.util.Set.of("id", "question_number", "question_type", "title", "content", "chapter_reference"), result.keySet());
        assertFalse(result.containsValue("PRIVATE_ANSWER"));
    }
    @Test void unknownNestedMetadataIsNotPassedThrough() throws Exception {
        var source = Map.<String, Object>of("chapters", java.util.List.of(Map.of("id", "x", "teacher", Map.of("score", 100),
            "qa", java.util.List.of(Map.of("question", "q", "grading_criteria", "hidden")))));
        String output = mapper.writeValueAsString(StudentContent.document(source));
        assertFalse(output.contains("hidden"));
        assertFalse(output.contains("teacher"));
        assertTrue(output.contains("q"));
    }
}
