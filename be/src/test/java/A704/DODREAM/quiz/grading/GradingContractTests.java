package A704.DODREAM.quiz.grading;
import org.junit.jupiter.api.Test;
import java.util.*;
import static A704.DODREAM.quiz.grading.GradingContract.*;
import static org.junit.jupiter.api.Assertions.*;
class GradingContractTests {
    final String key="00000000-0000-0000-0000-000000000001";
    Submission input(String body) throws Exception { return parse(key,9,JSON.readTree(body)); }
    final List<Item> items=List.of(new Item(1,0,1,"SHORT_ANSWER","q","question","snapshot"," exact ","snapshot-v1"));
    String result(String correct,String feedback) { return "[{\"question_id\":1,\"student_answer\":\" exact \",\"is_correct\":"+correct+",\"ai_feedback\":"+feedback+"}]"; }
    @Test void fingerprintHasStableCrossProcessGoldenEncoding() throws Exception {
        var actual=input("{\"answers\":[{\"quizId\":1,\"version\":0,\"answer\":\"a\"}]}");
        assertEquals("596e4380de26fdf8ded8247b6c46f6eb8b3a933ec2a0435880a912542f32908d",actual.fingerprint());
    }
    @Test void orderDoesNotChangeFingerprint() throws Exception {
        var a=input("{\"answers\":[{\"quizId\":2,\"version\":0,\"answer\":\"b\"},{\"quizId\":1,\"version\":2,\"answer\":\"a\"}]}");
        var b=input("{\"answers\":[{\"quizId\":1,\"version\":2,\"answer\":\"a\"},{\"quizId\":2,\"version\":0,\"answer\":\"b\"}]}");
        assertEquals(a.fingerprint(),b.fingerprint()); assertEquals(1,a.answers().get(0).quizId());
    }
    @Test void whitespaceAndVersionAndMaterialAreIdentityInputs() throws Exception {
        String json="{\"answers\":[{\"quizId\":1,\"version\":0,\"answer\":\" a \"}]}";
        var a=input(json); assertEquals(" a ",a.answers().get(0).answer());
        assertNotEquals(a.fingerprint(),input(json.replace(" a ","a")).fingerprint());
        assertNotEquals(a.fingerprint(),input(json.replace("version\":0","version\":1")).fingerprint());
        assertNotEquals(a.fingerprint(),parse(key,10,JSON.readTree(json)).fingerprint());
    }
    @Test void badKeysMissingVersionsAndCoercionsAreRejected() throws Exception {
        for(String bad:List.of("",key.toUpperCase().replace("00000000","AAAAAAAA"),"../../x","x".repeat(129))) assertThrows(GradingFailure.class,()->uuid(bad));
        assertThrows(GradingFailure.class,()->uuid(null));
        for(String value:List.of("null","-1","\"0\"","0.0","true")) assertThrows(GradingFailure.class,()->input("{\"answers\":[{\"quizId\":1,\"version\":"+value+",\"answer\":\"a\"}]}"));
        assertThrows(GradingFailure.class,()->input("{\"answers\":[{\"quizId\":1,\"answer\":\"a\"}]}"));
    }
    @Test void duplicateEmptyLargeAndExtraPayloadsAreRejected() throws Exception {
        String a="{\"quizId\":1,\"version\":0,\"answer\":\"a\"}";
        for(String json:List.of("{\"answers\":[]}","{\"answers\":["+a+","+a+"]}","{\"answers\":["+a.replace("\"a\"","\""+"x".repeat(2001)+"\"")+"]}")) assertThrows(GradingFailure.class,()->input(json));
        var array=JSON.createArrayNode();for(int i=1;i<=51;i++)array.addObject().put("quizId",i).put("version",0).put("answer","");
        assertThrows(GradingFailure.class,()->parse(key,1,JSON.createObjectNode().set("answers",array)));
    }
    @Test void clientAuthorityFieldsAreIgnoredAndExcludedFromFingerprint() throws Exception {
        String base="{\"answers\":[{\"quizId\":1,\"version\":0,\"answer\":\"a\"}]}";
        String forged="{\"studentId\":99,\"score\":100,\"answers\":[{\"quizId\":1,\"version\":0,\"answer\":\"a\",\"correct_answer\":\"forged\",\"is_correct\":true}]}";
        assertEquals(input(base).fingerprint(),input(forged).fingerprint());
    }
    @Test void validProviderUsesExactSnapshotAnswers() { assertEquals(1,provider(result("true","\"feedback\""),items).size()); }
    @Test void correctnessCannotBeCoerced() { for(String bad:List.of("null","1","0","\"true\"","{}")) assertThrows(GradingFailure.class,()->provider(result(bad,"\"ok\""),items)); }
    @Test void missingDuplicateWrongAndNonIntegralIdsAreRejected() {
        for(String raw:List.of("[]",result("true","\"ok\"").replace("\"question_id\":1","\"question_id\":2"),result("true","\"ok\"").replace("\"question_id\":1","\"question_id\":1.0"),result("true","\"ok\"").replace("\"question_id\":1","\"question_id\":1,\"question_id\":1"),result("true","\"ok\"")+" []")) assertThrows(GradingFailure.class,()->provider(raw,items));
    }
    @Test void feedbackNullOversizedAndMismatchedAnswersAreRejected() {
        for(String raw:List.of(result("true","null"),result("true","\""+"x".repeat(2001)+"\""),result("true","\"ok\"").replace(" exact ","exact"),result("true","\"ok\"").replace("\"is_correct\":true,",""))) assertThrows(GradingFailure.class,()->provider(raw,items));
    }
    @Test void maximumUnicodeAndEscapedControlShapeFitsBoundedTransport() throws Exception {
        for(String answer:List.of("😀".repeat(2000),String.valueOf((char)1).repeat(2000))) {
            var all=new ArrayList<Item>();var response=JSON.createArrayNode();
            for(int i=1;i<=50;i++) {
                all.add(new Item(i,0,i,"SHORT_ANSWER","q","question","snapshot",answer,"snapshot-v1"));
                response.addObject().put("question_id",i).put("student_answer",answer).put("is_correct",true).put("ai_feedback",answer);
            }
            String raw=JSON.writeValueAsString(response);
            assertTrue(raw.getBytes(java.nio.charset.StandardCharsets.UTF_8).length<2*1024*1024);
            assertEquals(50,provider(raw,all).size());
        }
    }
    @Test void unpairedSurrogatesCannotCreateAmbiguousUtf8Fingerprints() {
        for(String answer:List.of(String.valueOf((char)0xD800),String.valueOf((char)0xDC00))) {
            var array=JSON.createArrayNode();array.addObject().put("quizId",1).put("version",0).put("answer",answer);
            assertThrows(GradingFailure.class,()->parse(key,1,JSON.createObjectNode().set("answers",array)));
        }
    }
    @Test void retryRequiresFrozenGenerationAndExplicitBoolean() throws Exception {
        assertEquals(1,retry(JSON.readTree("{\"expectedGeneration\":1,\"confirmUnknown\":false}")).expectedGeneration());
        for(String bad:List.of("{}","{\"expectedGeneration\":1,\"confirmUnknown\":\"true\"}","{\"expectedGeneration\":4,\"confirmUnknown\":false}")) assertThrows(GradingFailure.class,()->retry(JSON.readTree(bad)));
    }
}
