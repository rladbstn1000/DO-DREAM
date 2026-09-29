package A704.DODREAM.quiz.service;
import A704.DODREAM.quiz.entity.StudentQuizLog;
import java.time.LocalDateTime;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class GradingStatisticsTests {
    final LocalDateTime at=LocalDateTime.of(2026,1,1,0,0);
    @Test void lateCompletionOfOldSubmissionCannotReplaceNewSubmission() {
        var old=StudentQuizLog.builder().id(10L).attemptId(1L).submittedAt(at).solvedAt(at.plusMinutes(5)).build();
        var newer=StudentQuizLog.builder().id(9L).attemptId(2L).submittedAt(at.plusSeconds(1)).solvedAt(at.plusSeconds(2)).build();
        assertSame(newer,QuizService.latest(old,newer)); assertSame(newer,QuizService.latest(newer,old));
    }
    @Test void nullableLegacyTimesUseDeterministicIdFallback() {
        var a=StudentQuizLog.builder().id(1L).build();
        var b=StudentQuizLog.builder().id(2L).build();
        assertSame(b,QuizService.latest(a,b));
    }
    @Test void tiesUseAcceptanceSequenceThenLogIdAndLegacyUsesOriginalTime() {
        var a=StudentQuizLog.builder().id(10L).attemptId(1L).submittedAt(at).solvedAt(at).build();
        var b=StudentQuizLog.builder().id(9L).attemptId(2L).submittedAt(at).solvedAt(at).build();
        assertSame(b,QuizService.latest(a,b));
        var legacy=StudentQuizLog.builder().id(20L).solvedAt(at.minusSeconds(1)).build();
        assertSame(a,QuizService.latest(a,legacy));
    }
}
