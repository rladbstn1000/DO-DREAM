package A704.DODREAM.local;

import A704.DODREAM.auth.entity.DeviceCredential;
import A704.DODREAM.auth.entity.PasswordCredential;
import A704.DODREAM.file.entity.UploadedFile;
import A704.DODREAM.file.enums.PostStatus;
import A704.DODREAM.material.entity.*;
import A704.DODREAM.material.enums.*;
import A704.DODREAM.quiz.entity.Quiz;
import A704.DODREAM.user.entity.*;
import jakarta.persistence.EntityManager;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.core.annotation.Order;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.UUID;

/** Separate, additive version 2 fixtures. Existing accounts, material bytes and relations are never reset. */
@Component
@Profile("local")
@Order(10)
@RequiredArgsConstructor
public class LocalAuthorizationFixtures implements ApplicationRunner {
    private final EntityManager em;
    private final PasswordEncoder encoder;
    private final LocalObjectStore objects;
    @Value("${LOCAL_TEACHER_PASSWORD}") private String password;
    @Value("${LOCAL_STUDENT_SECRET}") private String secret;
    public static final String BODY = """
        {"local_fixture":true,"chapters":[
          {"id":"authz-content","type":"content","title":"합성 물의 상태","content":"물은 차가워지면 얼음이 됩니다."},
          {"id":"authz-quiz","type":"quiz","title":"합성 개념 확인","qa":[
            {"id":"authz-question","question":"물이 차가워지면 무엇이 되나요?","answer":"AUTHZ_TEACHER_ONLY_ANSWER","correct_answer":"AUTHZ_TEACHER_ONLY_ANSWER","rubric":"AUTHZ_TEACHER_ONLY_RUBRIC"}],
           "teacher_notes":{"answer":"AUTHZ_TEACHER_ONLY_NESTED"}}
        ]}
        """;
    @Override @Transactional
    public void run(ApplicationArguments args) {
        if (em.createQuery("select count(p) from PasswordCredential p where p.email = :email", Long.class)
            .setParameter("email", "authz-owner@local.dodream.invalid").getSingleResult() > 0) return;
        School school = save(School.create("AUTHZ 합성 학교"));
        School remoteSchool = save(School.create("AUTHZ 다른 합성 학교"));
        Classroom ownerClass = classroom(school, 91), otherClass = classroom(school, 92), remoteClass = classroom(remoteSchool, 93);
        User owner = teacher("owner", ownerClass), other = teacher("other", otherClass), remote = teacher("remote", remoteClass);
        User shared = student("shared", ownerClass), unshared = student("unshared", ownerClass);
        User classShared = student("class", ownerClass), otherStudent = student("other", otherClass), remoteStudent = student("remote", remoteClass);
        Material editable = material(owner, "editable", PostStatus.PUBLISHED);
        share(editable, owner, shared, ownerClass, ShareType.INDIVIDUAL);
        Material second = material(owner, "second-shared", PostStatus.PUBLISHED);
        share(second, owner, shared, ownerClass, ShareType.INDIVIDUAL);
        Material classMaterial = material(owner, "class-shared", PostStatus.PUBLISHED);
        share(classMaterial, owner, classShared, ownerClass, ShareType.CLASS);
        material(owner, "private", PostStatus.PUBLISHED);
        material(owner, "draft", PostStatus.DRAFT);
        material(other, "other-owned", PostStatus.PUBLISHED);
        material(remote, "remote-owned", PostStatus.PUBLISHED);
        em.flush();
        if (em.createQuery("select t from TeacherProfile t where t.user.id = :id", TeacherProfile.class)
            .setParameter("id", owner.getId()).getSingleResult().getId() == owner.getId())
            throw new IllegalStateException("Authorization fixture must distinguish User and Profile IDs");
    }
    private Classroom classroom(School school, int number) {
        return save(Classroom.builder().school(school).year(2026).gradeLevel(9).classNumber(number).build());
    }
    private User teacher(String tag, Classroom classroom) {
        User user = save(User.create("AUTHZ 교사 " + tag, Role.TEACHER));
        TeacherProfile profile = save(TeacherProfile.create(user, "AUTHZ-TEACHER-" + tag));
        save(ClassroomTeacher.builder().teacher(profile).classroom(classroom).build());
        save(PasswordCredential.create(user, "authz-" + tag + "@local.dodream.invalid", encoder.encode(password)));
        return user;
    }
    private User student(String tag, Classroom classroom) {
        User user = save(User.create("AUTHZ 학생 " + tag, Role.STUDENT));
        save(StudentProfile.create(user, classroom.getSchool().getName(), "AUTHZ-STUDENT-" + tag, classroom, "UNSPECIFIED"));
        save(DeviceCredential.create(user, "dodream-authz-" + tag, "LOCAL_TEST", encoder.encode(secret)));
        return user;
    }
    private Material material(User owner, String tag, PostStatus status) {
        String key = "local/synthetic/authz/" + UUID.randomUUID() + ".json";
        objects.initialize(key, BODY.getBytes(StandardCharsets.UTF_8));
        UploadedFile file = save(UploadedFile.builder().originalFileName("authz-" + tag + ".json")
            .uploaderId(owner.getId()).s3Bucket("local-synthetic-fixtures").s3Key(key).jsonS3Key(key)
            .contentType("application/json").fileType("application/json").fileSize((long) BODY.getBytes(StandardCharsets.UTF_8).length)
            .parsedAt(LocalDateTime.now()).build());
        Material material = save(Material.builder().teacher(owner).uploadedFile(file).title("[AUTHZ LOCAL] " + tag)
            .subject("과학").gradeLevel("9").postStatus(status).label(LabelColor.BLUE).build());
        save(MaterialContent.builder().material(material).pageNumber(1).textContent("물은 차가워지면 얼음이 됩니다.").build());
        save(Quiz.builder().material(material).questionNumber(1).questionType("SHORT_ANSWER").title("합성 문제")
            .content("물이 차가워지면 무엇이 되나요?").correctAnswer("얼음").chapterReference("authz-content").build());
        return material;
    }
    private void share(Material material, User owner, User student, Classroom classroom, ShareType type) {
        save(MaterialShare.builder().material(material).teacher(owner).student(student).classroom(classroom).shareType(type).build());
    }
    private <T> T save(T entity) { em.persist(entity); return entity; }
}
