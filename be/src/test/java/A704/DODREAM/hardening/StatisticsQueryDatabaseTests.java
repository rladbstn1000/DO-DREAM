package A704.DODREAM.hardening;

import A704.DODREAM.file.entity.UploadedFile;
import A704.DODREAM.file.enums.PostStatus;
import A704.DODREAM.material.entity.*;
import A704.DODREAM.material.enums.ShareType;
import A704.DODREAM.quiz.entity.*;
import A704.DODREAM.quiz.service.QuizService;
import A704.DODREAM.user.entity.*;
import jakarta.persistence.EntityManager;
import org.hibernate.SessionFactory;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;
import static org.junit.jupiter.api.Assertions.*;

/** Fixed synthetic rows are rolled back; counts exclude fixture insertion and caches. */
@SpringBootTest(properties = "spring.jpa.properties.hibernate.generate_statistics=true")
@ActiveProfiles("local")
@Transactional
class StatisticsQueryDatabaseTests {
    @Autowired EntityManager em;
    @Autowired QuizService service;

    @Test void repeatedAttemptsUseBoundedAuthorizationLookups() {
        var school=save(School.create("hardening statistics synthetic"));
        var room=save(Classroom.builder().school(school).year(2026).gradeLevel(8).classNumber(96).build());
        var teacher=save(User.create("synthetic teacher",Role.TEACHER));
        var teacherProfile=save(TeacherProfile.create(teacher,"HARDENING-STATS"));
        save(ClassroomTeacher.builder().classroom(room).teacher(teacherProfile).build());
        var student=save(User.create("synthetic student",Role.STUDENT));
        save(StudentProfile.create(student,school.getName(),"HARDENING-STATS",room,"UNSPECIFIED"));
        var file=save(UploadedFile.builder().originalFileName("synthetic.json").uploaderId(teacher.getId()).build());
        var material=save(Material.builder().teacher(teacher).uploadedFile(file).title("fixed synthetic statistics")
            .postStatus(PostStatus.PUBLISHED).build());
        var share=save(MaterialShare.builder().teacher(teacher).student(student).material(material)
            .classroom(room).shareType(ShareType.INDIVIDUAL).build());
        for (int question=1;question<=2;question++) {
            var quiz=save(Quiz.builder().material(material).questionNumber(question).questionType("SHORT_ANSWER")
                .title("synthetic question").content("synthetic question").correctAnswer("synthetic answer").build());
            for (int repeat=0;repeat<10;repeat++) save(StudentQuizLog.builder().quiz(quiz).student(student)
                .studentAnswer("synthetic answer").isCorrect(question==1).build());
        }
        em.flush();
        Long studentId=student.getId(), shareId=share.getId();
        em.clear();
        var statistics=em.getEntityManagerFactory().unwrap(SessionFactory.class).getStatistics();
        statistics.clear();
        var byMaterial=service.getStudentStatsByMaterialList(studentId,studentId);
        long materialQueries=statistics.getPrepareStatementCount();
        assertEquals(1,byMaterial.size());
        assertEquals(2,byMaterial.get(0).getTotalQuizCount());
        assertEquals(20,byMaterial.get(0).getTryCount());
        assertEquals(20,byMaterial.get(0).getLegacyLogCount());
        assertEquals(50.0,byMaterial.get(0).getCorrectRate());
        em.clear(); statistics.clear();
        var overall=service.getStudentOverallStats(studentId,studentId);
        long overallQueries=statistics.getPrepareStatementCount();
        assertEquals(1,overall.getSolvedMaterialCount());
        assertEquals(50.0,overall.getAverageCorrectRate());
        System.out.println("HARDENING_STATISTICS_QUERY_COUNT materials="+materialQueries+" overall="+overallQueries+" materials_fixture=1 quizzes=2 logs=20");
        assertTrue(materialQueries <= 12, "Repeated logs must not repeat material authorization queries: "+materialQueries);
        assertTrue(overallQueries <= 12, "Repeated logs must not repeat material authorization queries: "+overallQueries);
        // Removing the current share must still hide all old history on the next request.
        em.remove(em.find(MaterialShare.class,shareId)); em.flush(); em.clear();
        assertTrue(service.getStudentStatsByMaterialList(studentId,studentId).isEmpty());
        assertEquals(0,service.getStudentOverallStats(studentId,studentId).getSolvedMaterialCount());
    }
    private <T> T save(T row) { em.persist(row); return row; }
}
