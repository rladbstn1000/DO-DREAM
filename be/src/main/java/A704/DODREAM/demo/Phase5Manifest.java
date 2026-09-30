package A704.DODREAM.demo;

import A704.DODREAM.indexing.*;
import A704.DODREAM.material.dto.PublishRequest;
import A704.DODREAM.material.enums.LabelColor;
import A704.DODREAM.quiz.dto.QuizSaveDto;
import com.fasterxml.jackson.databind.JsonNode;
import java.security.MessageDigest;
import java.util.*;

/** Fixed authored content + server quiz answers; evaluator labels never enter retrieval. */
public final class Phase5Manifest {
    private Phase5Manifest() {}
    public static final String VERSION="phase5-eval-v1";
    public static final String SPEC="openai-text-embedding-3-small-1536-l2-content-v1";
    public record Question(String caseId,String question,String answer,String chapter) {}
    public record Sample(String key,String title,String sourceHash,List<Map<String,Object>> chapters,List<Question> questions) {
        public String sampleKey(){return "phase5eval-"+key;}
        public Map<String,Object> document(){return Map.of("chapters",chapters,"fixtureVersion",VERSION);}
        public Map<String,Object> initial(){return document();}
        public PublishRequest publication(){
            List<QuizSaveDto> quizzes=new ArrayList<>();
            for(int i=0;i<questions.size();i++) {var q=questions.get(i);quizzes.add(QuizSaveDto.builder()
                .questionNumber(i+1).questionType("SHORT_ANSWER").title("평가 자료 확인 "+(i+1))
                .content(q.question()).correctAnswer(q.answer()).chapterReference(q.chapter()).build());}
            return PublishRequest.builder().materialTitle(title).labelColor(LabelColor.BLUE).editedJson(document()).quizzes(quizzes).build();
        }
    }
    public static final List<Sample> SAMPLES;
    public static final String RESOURCE_SHA256;
    static {
        try(var stream=Phase5Manifest.class.getResourceAsStream("/demo/phase5-materials.json")) {
            if(stream==null)throw new IllegalStateException();
            byte[] bytes=stream.readAllBytes();
            RESOURCE_SHA256=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
            JsonNode root=IndexingSource.JSON.readTree(bytes);
            if(!VERSION.equals(root.path("fixture_version").asText()) || root.path("materials").size()!=4)throw new IllegalStateException();
            var samples=new ArrayList<Sample>();var keys=new HashSet<String>();
            for(var m:root.path("materials")) {
                String key=m.path("material_key").asText();
                if(!key.matches("[a-z0-9-]{1,60}") || !keys.add(key))throw new IllegalStateException();
                List<Map<String,Object>> chapters=new ArrayList<>();
                for(var c:m.path("chapters")) {
                    if(!"content".equals(c.path("type").asText()))throw new IllegalStateException();
                    chapters.add(Map.of("id",c.path("id").asText(),"type","content","title",c.path("title").asText(),"content",c.path("content").asText()));
                }
                var questions=new ArrayList<Question>();
                for(var q:m.path("quizzes")) questions.add(new Question(q.path("evaluation_case_id").asText(""),q.path("question").asText(),q.path("correct_answer").asText(),q.path("chapter_source_id").asText()));
                var sample=new Sample(key,m.path("title").asText(),m.path("source_hash").asText(),List.copyOf(chapters),List.copyOf(questions));
                if(!IndexingSource.material(sample.document()).hash().equals(sample.sourceHash()) || questions.isEmpty() || questions.size()>8)throw new IllegalStateException();
                samples.add(sample);
            }
            SAMPLES=List.copyOf(samples);
        } catch(Exception invalid) {throw new ExceptionInInitializerError("Invalid fixed phase 5 server fixture");}
    }
}
