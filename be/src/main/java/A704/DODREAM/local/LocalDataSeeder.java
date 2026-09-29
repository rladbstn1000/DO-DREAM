package A704.DODREAM.local;

import A704.DODREAM.auth.entity.DeviceCredential;
import A704.DODREAM.auth.entity.PasswordCredential;
import A704.DODREAM.file.entity.UploadedFile;
import A704.DODREAM.file.enums.PostStatus;
import A704.DODREAM.material.entity.Material;
import A704.DODREAM.material.entity.MaterialContent;
import A704.DODREAM.material.entity.MaterialShare;
import A704.DODREAM.material.enums.LabelColor;
import A704.DODREAM.material.enums.ShareType;
import A704.DODREAM.quiz.entity.Quiz;
import A704.DODREAM.user.entity.*;
import jakarta.persistence.EntityManager;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/** Version 1 seed: one transaction, inserted only once, never resets existing data or passwords. */
@Component
@Profile("local")
@RequiredArgsConstructor
@Slf4j
public class LocalDataSeeder implements ApplicationRunner {
    private final EntityManager entityManager;
    private final PasswordEncoder encoder;
    @Value("${LOCAL_TEACHER_PASSWORD}") private String teacherPassword;
    @Value("${LOCAL_STUDENT_SECRET}") private String studentSecret;

    @Override
    @Transactional
    public void run(ApplicationArguments args) {
        if (teacherPassword.isBlank() || studentSecret.isBlank()) {
            throw new IllegalStateException("Local synthetic account secrets must be supplied");
        }
        Long count = entityManager.createQuery(
            "select count(p) from PasswordCredential p where p.email = :email", Long.class)
            .setParameter("email", "teacher@local.dodream.invalid").getSingleResult();
        if (count > 0) {
            log.info("Local synthetic seed already exists; preserving stored data and credentials");
            return;
        }
        User teacher = save(User.create("합성 교사", Role.TEACHER));
        TeacherProfile teacherProfile = save(TeacherProfile.create(teacher, "LOCAL-TEACHER-001"));
        save(PasswordCredential.create(teacher, "teacher@local.dodream.invalid", encoder.encode(teacherPassword)));
        School school = save(School.create("로컬 합성 학교"));
        Classroom classroom = save(Classroom.builder().school(school).year(2026).gradeLevel(1).classNumber(1).build());
        save(ClassroomTeacher.builder().classroom(classroom).teacher(teacherProfile).build());
        User student = save(User.create("합성 학생", Role.STUDENT));
        save(StudentProfile.create(student, school.getName(), "LOCAL-STUDENT-001", classroom, "UNSPECIFIED"));
        save(DeviceCredential.create(student, "dodream-local-student", "LOCAL_TEST", encoder.encode(studentSecret)));
        Material material = lesson(teacher, "[LOCAL 합성 자료] 물의 상태");
        save(MaterialShare.builder().material(material).teacher(teacher).student(student)
            .classroom(classroom).shareType(ShareType.INDIVIDUAL).build());
        User otherTeacher = save(User.create("합성 타 교사", Role.TEACHER));
        save(TeacherProfile.create(otherTeacher, "LOCAL-TEACHER-002"));
        save(PasswordCredential.create(otherTeacher, "other-teacher@local.dodream.invalid", encoder.encode(teacherPassword)));
        lesson(teacher, "[LOCAL 비공유 합성 자료] 물의 상태");
        log.info("Local synthetic accounts, classroom, two materials and quizzes inserted; no external provider was called");
    }

    private Material lesson(User teacher, String title) {
        UploadedFile file = save(UploadedFile.builder().originalFileName("synthetic-lesson.json")
            .fileSize((long) LocalExternalConfiguration.fixture(LocalExternalConfiguration.FIXTURE_KEY).length)
            .fileType("application/json").contentType("application/json").uploaderId(teacher.getId())
            .s3Bucket("local-synthetic-fixtures").s3Key(LocalExternalConfiguration.FIXTURE_KEY)
            .jsonS3Key(LocalExternalConfiguration.FIXTURE_KEY).parsedAt(java.time.LocalDateTime.now()).build());
        Material material = save(Material.builder().teacher(teacher).uploadedFile(file)
            .title(title).subject("과학").gradeLevel("1").postStatus(PostStatus.PUBLISHED).label(LabelColor.BLUE).build());
        save(MaterialContent.builder().material(material).pageNumber(1)
            .textContent("물은 차가워지면 얼음이 됩니다. 얼음은 따뜻해지면 물이 됩니다. (합성 자료)").build());
        save(Quiz.builder().material(material).questionNumber(1).questionType("SHORT_ANSWER")
            .title("합성 문제 1").content("물이 차가워지면 무엇이 되나요?").correctAnswer("얼음")
            .chapterReference("local-chapter-1").build());
        return material;
    }

    private <T> T save(T entity) {
        entityManager.persist(entity);
        return entity;
    }
}
