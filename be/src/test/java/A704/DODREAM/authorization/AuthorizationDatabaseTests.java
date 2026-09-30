package A704.DODREAM.authorization;

import A704.DODREAM.file.entity.UploadedFile;
import A704.DODREAM.file.enums.PostStatus;
import A704.DODREAM.local.LocalExternalConfiguration;
import A704.DODREAM.material.entity.*;
import A704.DODREAM.material.enums.ShareType;
import A704.DODREAM.user.entity.*;
import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;
import static org.junit.jupiter.api.Assertions.*;

/** Actual JPA/MySQL relationship checks; every test rolls back its own additive rows. */
@SpringBootTest
@ActiveProfiles("local")
@Transactional
class AuthorizationDatabaseTests {
    @Autowired EntityManager em;
    @Autowired AuthorizationPolicy policy;
    @Autowired org.springframework.context.ApplicationContext context;
    User owner, outsider, student, peer;
    TeacherProfile ownerProfile;
    Classroom classroom;
    ClassroomTeacher assignment;
    Material material;
    MaterialShare share;
    StudentProfile studentProfile;
    @BeforeEach void fixtures() {
        var school = save(School.create("AUTHZ transactional test"));
        classroom = save(Classroom.builder().school(school).year(2026).gradeLevel(8).classNumber(97).build());
        owner = save(User.create("test owner", Role.TEACHER));
        outsider = save(User.create("test outsider", Role.TEACHER));
        ownerProfile = save(TeacherProfile.create(owner, "TEST-AUTHZ-OWNER"));
        save(TeacherProfile.create(outsider, "TEST-AUTHZ-OTHER"));
        assignment = save(ClassroomTeacher.builder().classroom(classroom).teacher(ownerProfile).build());
        student = save(User.create("test shared", Role.STUDENT));
        peer = save(User.create("test same classroom", Role.STUDENT));
        studentProfile = save(StudentProfile.create(student, school.getName(), "AUTHZ-T1", classroom, "UNSPECIFIED"));
        save(StudentProfile.create(peer, school.getName(), "AUTHZ-T2", classroom, "UNSPECIFIED"));
        var file = save(UploadedFile.builder().originalFileName("test.json").uploaderId(owner.getId())
            .s3Key(LocalExternalConfiguration.FIXTURE_KEY).jsonS3Key(LocalExternalConfiguration.FIXTURE_KEY).build());
        material = save(Material.builder().teacher(owner).uploadedFile(file).title("AUTHZ test material").postStatus(PostStatus.PUBLISHED).build());
        share = save(MaterialShare.builder().material(material).teacher(owner).student(student).classroom(classroom).shareType(ShareType.INDIVIDUAL).build());
        em.flush();
        assertNotEquals(owner.getId(), Long.valueOf(ownerProfile.getId()));
        assertNotEquals(student.getId(), studentProfile.getId());
    }
    @Test void realOwnerAndExplicitSharedStudentAreAllowed() {
        assertEquals(material.getId(), policy.owned(owner.getId(), material.getId()).getId());
        assertEquals(material.getId(), policy.studentMaterial(student.getId(), material.getId()).getId());
    }
    @Test void sameClassWithoutShareAndUnrelatedTeacherAreHidden() {
        hidden(() -> policy.studentMaterial(peer.getId(), material.getId()));
        hidden(() -> policy.owned(outsider.getId(), material.getId()));
        hidden(() -> policy.studentHistory(outsider.getId(), student.getId(), material.getId()));
    }
    @Test void revokingShareTakesEffectOnTheNextLookup() {
        policy.studentMaterial(student.getId(), material.getId());
        em.remove(share); em.flush();
        hidden(() -> policy.studentMaterial(student.getId(), material.getId()));
    }
    @Test void revokingAssignmentAlsoRevokesIndividualShareAndTeacherHistory() {
        policy.studentHistory(owner.getId(), student.getId(), material.getId());
        em.remove(assignment); em.flush();
        hidden(() -> policy.studentMaterial(student.getId(), material.getId()));
        hidden(() -> policy.studentHistory(owner.getId(), student.getId(), material.getId()));
    }
    @Test void classShareRequiresExplicitRowAndCurrentClass() {
        em.remove(share); em.flush();
        save(MaterialShare.builder().material(material).teacher(owner).student(student).classroom(classroom).shareType(ShareType.CLASS).build());
        em.flush();
        policy.studentMaterial(student.getId(), material.getId());
        hidden(() -> policy.studentMaterial(peer.getId(), material.getId()));
        var other = save(Classroom.builder().school(classroom.getSchool()).year(2026).gradeLevel(8).classNumber(98).build());
        save(ClassroomTeacher.builder().teacher(ownerProfile).classroom(other).build());
        studentProfile.setClassroom(other); em.flush();
        hidden(() -> policy.studentMaterial(student.getId(), material.getId()));
    }
    @Test void draftDeletedAndContradictoryShareAreHidden() {
        material.setPostStatus(PostStatus.DRAFT); em.flush();
        hidden(() -> policy.studentMaterial(student.getId(), material.getId()));
        material.setPostStatus(PostStatus.PUBLISHED);
        em.remove(share); em.flush();
        save(MaterialShare.builder().material(material).teacher(outsider).student(student).classroom(classroom).shareType(ShareType.INDIVIDUAL).build());
        em.flush(); hidden(() -> policy.studentMaterial(student.getId(), material.getId()));
        material.softDelete(); em.flush(); hidden(() -> policy.owned(owner.getId(), material.getId()));
    }
    @Test void teacherCannotUseSharedStudentAsPermissionForAnotherOwnersMaterial() {
        material.setTeacher(outsider); em.flush();
        hidden(() -> policy.studentHistory(owner.getId(), student.getId(), material.getId()));
        hidden(() -> policy.ownedFile(owner.getId(), material.getUploadedFile().getId()));
    }
    @Test void teacherListDoesNotRevealContradictoryLinkedFile() {
        material.setTeacher(outsider); em.flush();
        var response = context.getBean(A704.DODREAM.material.service.PublishService.class)
            .getPublishedMaterialList(outsider.getId());
        assertEquals(0, response.getMaterials().size());
    }
    @Test void fileOperationsRejectStudentRoleBeforeObjectLookup() {
        assertEquals(HttpStatus.FORBIDDEN, assertThrows(AuthorizationFailure.class,
            () -> policy.ownedFile(student.getId(), material.getUploadedFile().getId())).getStatus());
    }
    @Test void realDatabaseDenialDoesNotSignOrAccessObjectStorage() {
        var files = org.mockito.Mockito.mock(A704.DODREAM.file.repository.UploadedFileRepository.class);
        var storage = org.mockito.Mockito.mock(A704.DODREAM.file.service.S3Service.class);
        var signer = org.mockito.Mockito.mock(A704.DODREAM.file.service.CloudFrontService.class);
        var controller = new A704.DODREAM.file.controller.FileUploadController(policy, files, storage, signer);
        hidden(() -> controller.download(new A704.DODREAM.auth.dto.request.UserPrincipal(outsider.getId(), "other", "TEACHER"), material.getUploadedFile().getId()));
        org.mockito.Mockito.verifyNoInteractions(files, storage, signer);
    }
    @Test void mixedShareTargetsCauseNoPartialWriteStorageOrNotification() throws Exception {
        var repo = context.getBean(A704.DODREAM.material.repository.MaterialShareRepository.class);
        var storage = org.mockito.Mockito.mock(software.amazon.awssdk.services.s3.S3Client.class);
        var notifications = org.mockito.Mockito.mock(A704.DODREAM.fcm.service.FcmService.class);
        var service = new A704.DODREAM.material.service.MaterialShareService(policy, context.getBean(A704.DODREAM.indexing.IndexingStore.class), repo,
            context.getBean(A704.DODREAM.material.repository.MaterialRepository.class),
            context.getBean(A704.DODREAM.user.repository.UserRepository.class),
            context.getBean(A704.DODREAM.user.repository.ClassroomRepository.class),
            context.getBean(A704.DODREAM.file.repository.UploadedFileRepository.class), storage,
            new com.fasterxml.jackson.databind.ObjectMapper(), notifications);
        String json = "{\"materialId\":" + material.getId() + ",\"shares\":{\"" + classroom.getId()
            + "\":{\"type\":\"INDIVIDUAL\",\"studentIds\":[" + peer.getId() + "," + outsider.getId() + "]}}}";
        var request = new com.fasterxml.jackson.databind.ObjectMapper().readValue(json, A704.DODREAM.material.dto.MaterialShareRequest.class);
        long before = repo.count();
        hidden(() -> service.shareMaterial(request, owner.getId()));
        assertEquals(before, repo.count());
        org.mockito.Mockito.verifyNoInteractions(storage, notifications);
    }
    @Test void realDatabaseDeniedSubmissionDoesNotReadQuestionsOrGrade() {
        var db = org.mockito.Mockito.mock(org.springframework.jdbc.core.JdbcTemplate.class);
        var hooks = org.mockito.Mockito.mock(A704.DODREAM.quiz.grading.GradingLocalHooks.class);
        var tx = org.mockito.Mockito.mock(org.springframework.transaction.PlatformTransactionManager.class);
        org.mockito.Mockito.when(tx.getTransaction(org.mockito.ArgumentMatchers.any())).thenReturn(new org.springframework.transaction.support.SimpleTransactionStatus());
        var store = new A704.DODREAM.quiz.grading.GradingStore(db,policy,tx,hooks,em,em.getEntityManagerFactory());
        var input = new A704.DODREAM.quiz.grading.GradingContract.Submission("00000000-0000-0000-0000-000000000001","synthetic",java.util.List.of());
        hidden(() -> store.accept(peer.getId(), material.getId(), input));
        org.mockito.Mockito.verifyNoInteractions(db,hooks);
    }

    @Test void legitimateQuizEditPreservesExistingStudentLogForeignKey() {
        var quiz = save(A704.DODREAM.quiz.entity.Quiz.builder().material(material).questionNumber(1)
            .questionType("SHORT_ANSWER").title("before").content("before").correctAnswer("answer").build());
        var log = save(A704.DODREAM.quiz.entity.StudentQuizLog.builder().quiz(quiz).student(student)
            .studentAnswer("answer").isCorrect(true).aiFeedback("feedback").build());
        em.flush();
        var service = context.getBean(A704.DODREAM.quiz.service.QuizService.class);
        service.saveQuizzes(material.getId(), owner.getId(), java.util.List.of(
            A704.DODREAM.quiz.dto.QuizSaveDto.builder().questionNumber(1).questionType("SHORT_ANSWER")
                .title("after").content("after").correctAnswer("answer").build()));
        em.flush();
        assertEquals(quiz.getId(), log.getQuiz().getId());
        assertEquals("after", log.getQuiz().getContent());
        assertEquals(HttpStatus.CONFLICT, assertThrows(AuthorizationFailure.class,
            () -> service.validateEdits(material.getId(), java.util.List.of())).getStatus());
    }
    private void hidden(Runnable action) { assertEquals(HttpStatus.NOT_FOUND, assertThrows(AuthorizationFailure.class, action::run).getStatus()); }
    private <T> T save(T entity) { em.persist(entity); return entity; }
}
