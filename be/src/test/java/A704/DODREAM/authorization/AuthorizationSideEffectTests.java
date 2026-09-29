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
    @Test void deniedGradingDoesNotReadQuestionsOrScheduleWork() throws Exception {
        var policy = mock(AuthorizationPolicy.class);
        var db = mock(org.springframework.jdbc.core.JdbcTemplate.class);
        var hooks = mock(A704.DODREAM.quiz.grading.GradingLocalHooks.class);
        var em = mock(jakarta.persistence.EntityManager.class);
        when(policy.studentMaterial(21L,73L)).thenThrow(AuthorizationPolicy.hidden());
        var tx = mock(org.springframework.transaction.PlatformTransactionManager.class);
        when(tx.getTransaction(any())).thenReturn(new org.springframework.transaction.support.SimpleTransactionStatus());
        var store = new A704.DODREAM.quiz.grading.GradingStore(db, policy, tx, hooks, em, mock(jakarta.persistence.EntityManagerFactory.class));
        var input = A704.DODREAM.quiz.grading.GradingContract.parse("00000000-0000-0000-0000-000000000001",73L,
            new com.fasterxml.jackson.databind.ObjectMapper().readTree("{\"answers\":[{\"quizId\":999,\"version\":0,\"answer\":\"x\"}]}"));
        assertThrows(AuthorizationFailure.class, () -> store.accept(21,73,input));
        verifyNoInteractions(db,hooks);
    }
    @Test void mismatchedQuizIdIsRejectedBeforeGradingOrLogWrite() throws Exception {
        var policy = mock(AuthorizationPolicy.class);
        var db = mock(org.springframework.jdbc.core.JdbcTemplate.class);
        var hooks = mock(A704.DODREAM.quiz.grading.GradingLocalHooks.class);
        var tx = mock(org.springframework.transaction.PlatformTransactionManager.class);
        when(tx.getTransaction(any())).thenReturn(new org.springframework.transaction.support.SimpleTransactionStatus());
        var store = new A704.DODREAM.quiz.grading.GradingStore(db,policy,tx,hooks,mock(jakarta.persistence.EntityManager.class),mock(jakarta.persistence.EntityManagerFactory.class));
        when(db.query(eq("SELECT * FROM grading_attempts WHERE attempt_id=?"), org.mockito.ArgumentMatchers.<org.springframework.jdbc.core.RowMapper<A704.DODREAM.quiz.grading.GradingContract.Attempt>>any(), anyString())).thenReturn(List.of(
            new A704.DODREAM.quiz.grading.GradingContract.Attempt(1,"00000000-0000-0000-0000-000000000001",21,73,"key","fingerprint","READY",0,null,null,java.time.LocalDateTime.now(),null)));
        var input = A704.DODREAM.quiz.grading.GradingContract.parse("00000000-0000-0000-0000-000000000001",73L,
            new com.fasterxml.jackson.databind.ObjectMapper().readTree("{\"answers\":[{\"quizId\":999,\"version\":0,\"answer\":\"x\"}]}"));
        var error = assertThrows(AuthorizationFailure.class, () -> store.accept(21,73,input));
        assertEquals(HttpStatus.BAD_REQUEST,error.getStatus());
        verify(db,never()).update(contains("student_quiz_logs"),any(Object[].class));
        verify(tx).rollback(any());
        verifyNoInteractions(hooks);
    }
}
