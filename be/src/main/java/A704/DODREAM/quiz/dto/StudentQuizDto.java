package A704.DODREAM.quiz.dto;

import A704.DODREAM.quiz.entity.Quiz;
import com.fasterxml.jackson.annotation.JsonProperty;

public record StudentQuizDto(Long id, long version, @JsonProperty("question_number") Integer questionNumber,
    @JsonProperty("question_type") String questionType, String title, String content,
    @JsonProperty("chapter_reference") String chapterReference) {
    public static StudentQuizDto from(Quiz quiz) {
        return new StudentQuizDto(quiz.getId(), quiz.getVersion(), quiz.getQuestionNumber(), quiz.getQuestionType(),
            quiz.getTitle(), quiz.getContent(), quiz.getChapterReference());
    }
}
