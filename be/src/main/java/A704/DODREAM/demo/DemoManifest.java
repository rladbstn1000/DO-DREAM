package A704.DODREAM.demo;

import A704.DODREAM.material.dto.PublishRequest;
import A704.DODREAM.material.enums.LabelColor;
import A704.DODREAM.quiz.dto.QuizSaveDto;
import java.util.*;

/** Authored synthetic learning content. Answers exist only in this server fixture and quiz storage. */
public final class DemoManifest {
    private DemoManifest() {}
    public static final String VERSION="student-web-phase5-v1";
    public static final String TEACHER_EMAIL="demo-phase5-v1@local.dodream.invalid";
    public static final String SOURCE="DO:DREAM 로컬 체험용 직접 작성 · v1";
    public record Section(String id,String title,String text) {}
    public record Question(String text,String answer,String chapter) {}
    public record Sample(String key,String title,String description,List<Section> sections,List<Question> questions) {
        public Map<String,Object> document() {
            List<Map<String,Object>> chapters=new ArrayList<>();
            for(var s:sections) chapters.add(Map.of("id",s.id(),"type","content","title",s.title(),"content",s.text()));
            return Map.of("chapters",chapters,"source",SOURCE,"fixtureVersion",VERSION);
        }
        public Map<String,Object> initial() {
            var titles=sections.stream().map(s->Map.of("title",s.title(),"s_titles",List.of(Map.of("s_title","","contents",s.text())))).toList();
            return Map.of("data",List.of(Map.of("index",key,"index_title",title,"titles",titles)),"indexes",sections.stream().map(Section::title).toList());
        }
        public PublishRequest publication() {
            List<QuizSaveDto> quizzes=new ArrayList<>();
            for(int i=0;i<questions.size();i++) { var q=questions.get(i); quizzes.add(QuizSaveDto.builder().questionNumber(i+1)
                .questionType("SHORT_ANSWER").title("배운 내용 확인 "+(i+1)).content(q.text()).correctAnswer(q.answer()).chapterReference(q.chapter()).build()); }
            return PublishRequest.builder().materialTitle(title).labelColor(LabelColor.BLUE).editedJson(document()).quizzes(quizzes).build();
        }
    }
    public static final List<Sample> SAMPLES=List.of(
        new Sample("water-phase5-v1","물의 여행","물이 모습을 바꾸고 다시 돌아오는 길을 함께 살펴봐요.",List.of(
            new Section("water-1","얼음과 물","물은 주변의 온도에 따라 모습이 달라집니다. 물이 충분히 차가워지면 단단한 얼음이 됩니다. 얼음을 따뜻한 곳에 두면 다시 물이 됩니다."),
            new Section("water-2","하늘로 올라가는 물","젖은 수건을 널어 두면 조금씩 마릅니다. 수건 속 물이 눈에 보이지 않는 수증기가 되어 공기 중으로 나가기 때문입니다. 액체인 물이 기체로 바뀌는 일을 증발이라고 합니다."),
            new Section("water-3","다시 땅으로 돌아오는 물","하늘의 수증기가 차가워지면 작은 물방울이 생깁니다. 작은 물방울이 모여 구름을 이룹니다. 물방울이 커지고 무거워지면 비가 되어 내려옵니다. 물은 이렇게 여러 모습을 바꾸며 여행합니다.")),
            List.of(new Question("물이 충분히 차가워지면 무엇이 되나요?","얼음","water-1"),new Question("액체인 물이 기체로 바뀌는 일을 무엇이라고 하나요?","증발","water-2"))),
        new Sample("recycling-phase5-v1","생활 속 분리배출","사용한 물건을 살펴보고 알맞게 나누어 버려요.",List.of(
            new Section("recycling-1","먼저 비우고 헹구기","분리배출은 사용한 물건을 재질에 따라 나누어 버리는 일입니다. 음료가 담겼던 용기는 내용물을 먼저 비웁니다. 음식물이 묻었다면 가볍게 헹굽니다. 깨끗하게 나누어 모으면 다시 쓸 수 있는 자원이 됩니다."),
            new Section("recycling-2","종이와 용기 살펴보기","깨끗한 종이는 젖지 않게 모읍니다. 상자에 붙은 테이프처럼 다른 재질은 떼어 냅니다. 용기에도 서로 다른 재질의 뚜껑이나 라벨이 붙어 있을 수 있습니다. 분리할 수 있는 부분은 나누어 모읍니다."),
            new Section("recycling-3","안내를 확인하기","모든 물건을 같은 곳에 버리지는 않습니다. 사는 곳마다 분리배출 장소와 날짜가 다를 수 있습니다. 헷갈릴 때는 거주 지역의 분리배출 안내를 확인합니다. 무조건 재활용함에 넣기보다 안내에 맞게 버리는 것이 중요합니다.")),
            List.of(new Question("음료 용기를 분리배출하기 전에 내용물을 먼저 어떻게 해야 하나요?","비웁니다","recycling-1"),new Question("분리배출 방법이 헷갈릴 때는 거주 지역의 무엇을 확인하나요?","분리배출 안내","recycling-3")))
    );
}
