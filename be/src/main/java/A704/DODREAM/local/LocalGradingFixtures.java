package A704.DODREAM.local;

import A704.DODREAM.file.entity.UploadedFile;
import A704.DODREAM.file.enums.PostStatus;
import A704.DODREAM.material.entity.*;
import A704.DODREAM.material.enums.*;
import A704.DODREAM.quiz.entity.Quiz;
import A704.DODREAM.user.entity.*;
import jakarta.persistence.EntityManager;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.*;
import org.springframework.context.annotation.Profile;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.UUID;

@Component @Profile("local") @Order(20) @RequiredArgsConstructor
public class LocalGradingFixtures implements ApplicationRunner {
    private final EntityManager em;
    private final LocalObjectStore objects;
    @Override @Transactional public void run(ApplicationArguments args) {
        User owner=em.createQuery("select p.user from PasswordCredential p where p.email=:email",User.class).setParameter("email","authz-owner@local.dodream.invalid").getSingleResult();
        for(String suffix:new String[]{"phase3a","phase3a second"}) {
            String title="[GRADING LOCAL] "+suffix;
            if(em.createQuery("select count(m) from Material m where m.title=:title",Long.class).setParameter("title",title).getSingleResult()>0) continue;
            String key="local/synthetic/authz/"+UUID.randomUUID()+".json";
            objects.initialize(key,LocalAuthorizationFixtures.BODY.getBytes(StandardCharsets.UTF_8));
            UploadedFile file=save(UploadedFile.builder().originalFileName("grading-synthetic.json").uploaderId(owner.getId()).s3Bucket("local-synthetic-fixtures").s3Key(key).jsonS3Key(key).contentType("application/json").fileType("application/json").fileSize((long)LocalAuthorizationFixtures.BODY.getBytes(StandardCharsets.UTF_8).length).parsedAt(LocalDateTime.now()).build());
            Material material=save(Material.builder().teacher(owner).uploadedFile(file).title(title).subject("과학").gradeLevel("9").postStatus(PostStatus.PUBLISHED).label(LabelColor.BLUE).build());
            save(MaterialContent.builder().material(material).pageNumber(1).textContent("합성 채점 검증용 자료").build());
            for(int n=1;n<=2;n++) save(Quiz.builder().material(material).questionNumber(n).questionType("SHORT_ANSWER").title("합성 채점 문제 "+n).content(n==1?"물이 얼면 무엇이 되나요?":"얼음이 녹으면 무엇이 되나요?").correctAnswer(n==1?"얼음":"물").chapterReference("authz-content").build());
            for(String device:new String[]{"dodream-authz-shared","dodream-authz-class"}) {
                User student=em.createQuery("select d.user from DeviceCredential d where d.deviceId=:device",User.class).setParameter("device",device).getSingleResult();
                StudentProfile profile=em.createQuery("select s from StudentProfile s where s.user.id=:id",StudentProfile.class).setParameter("id",student.getId()).getSingleResult();
                save(MaterialShare.builder().material(material).teacher(owner).student(student).classroom(profile.getClassroom()).shareType(ShareType.INDIVIDUAL).build());
            }
        }
    }
    private <T> T save(T value) { em.persist(value); return value; }
}
