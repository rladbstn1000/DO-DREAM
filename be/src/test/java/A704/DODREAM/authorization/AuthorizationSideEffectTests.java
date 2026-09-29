package A704.DODREAM.authorization;

import A704.DODREAM.auth.dto.request.UserPrincipal;
import A704.DODREAM.file.controller.FileUploadController;
import A704.DODREAM.file.repository.UploadedFileRepository;
import A704.DODREAM.file.service.*;
import A704.DODREAM.material.repository.MaterialRepository;
import A704.DODREAM.quiz.repository.*;
import A704.DODREAM.quiz.service.QuizService;
import A704.DODREAM.quiz.dto.QuizSubmissionDto;
import A704.DODREAM.user.repository.UserRepository;
import A704.DODREAM.user.entity.*;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.function.client.WebClient;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class AuthorizationSideEffectTests {
    @Test void providerBoundaryRetains503AndDoesNotExposeItsReason() {
        var result = new AuthorizationFailureHandler().boundary(new org.springframework.web.server.ResponseStatusException(
            HttpStatus.SERVICE_UNAVAILABLE, "synthetic private reason"));
        assertEquals(HttpStatus.SERVICE_UNAVAILABLE, result.getStatusCode());
        assertFalse(result.getBody().toString().contains("private"));
    }
    @Test void relationDatabaseFailureDoesNotBecomeAnAllowDecision() {
        var users = mock(UserRepository.class);
        var policy = new AuthorizationPolicy(users,
            mock(A704.DODREAM.user.repository.TeacherProfileRepository.class),
            mock(A704.DODREAM.user.repository.StudentProfileRepository.class),
            mock(A704.DODREAM.user.repository.ClassroomTeacherRepository.class),
            mock(MaterialRepository.class), mock(A704.DODREAM.material.repository.MaterialShareRepository.class),
            mock(UploadedFileRepository.class));
        when(users.findById(21L)).thenThrow(new org.springframework.dao.DataAccessResourceFailureException("synthetic failure"));
        assertThrows(org.springframework.dao.DataAccessException.class, () -> policy.studentMaterial(21L, 73L));
    }
    @Test void deniedDownloadDoesNotSignOrReadStorage() {
        var policy = mock(AuthorizationPolicy.class);
        var files = mock(UploadedFileRepository.class);
        var storage = mock(S3Service.class);
        var signer = mock(CloudFrontService.class);
        when(policy.ownedFile(21L, 73L)).thenThrow(AuthorizationPolicy.hidden());
        var controller = new FileUploadController(policy, files, storage, signer);
        var error = assertThrows(AuthorizationFailure.class, () -> controller.download(new UserPrincipal(21L, "t", "TEACHER"), 73L));
        assertEquals(HttpStatus.NOT_FOUND, error.getStatus());
        verifyNoInteractions(files, storage, signer);
    }
    @Test void deniedGradingDoesNotReadQuestionsOrScheduleWork() {
        var policy = mock(AuthorizationPolicy.class);
        var quizzes = mock(QuizRepository.class);
        var logs = mock(StudentQuizLogRepository.class);
        var material = mock(MaterialRepository.class);
        var users = mock(UserRepository.class);
        var client = mock(WebClient.class);
        when(policy.studentMaterial(21L, 73L)).thenThrow(AuthorizationPolicy.hidden());
        var service = new QuizService(policy, quizzes, logs, material, users, client);
        assertThrows(AuthorizationFailure.class, () -> service.gradeAndLog(73L, 21L, new QuizSubmissionDto(), "synthetic"));
        verifyNoInteractions(quizzes, logs, material, users, client);
    }
    @Test void mismatchedQuizIdIsRejectedBeforeGradingOrLogWrite() throws Exception {
        var policy = mock(AuthorizationPolicy.class);
        var quizzes = mock(QuizRepository.class);
        var logs = mock(StudentQuizLogRepository.class);
        var client = mock(WebClient.class);
        var service = new QuizService(policy, quizzes, logs, mock(MaterialRepository.class), mock(UserRepository.class), client);
        when(policy.role(21L, Role.STUDENT)).thenReturn(User.create("s", Role.STUDENT));
        when(quizzes.findAllByMaterialIdOrderByQuestionNumber(73L)).thenReturn(List.of());
        var submission = new com.fasterxml.jackson.databind.ObjectMapper().readValue("{\"answers\":[{\"quizId\":999,\"answer\":\"x\"}]}", QuizSubmissionDto.class);
        var error = assertThrows(AuthorizationFailure.class, () -> service.gradeAndLog(73L, 21L, submission, "synthetic"));
        assertEquals(HttpStatus.BAD_REQUEST, error.getStatus());
        verifyNoInteractions(logs, client);
    }
}
