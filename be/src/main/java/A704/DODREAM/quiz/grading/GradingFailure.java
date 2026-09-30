package A704.DODREAM.quiz.grading;
public final class GradingFailure extends RuntimeException {
    public final int status;
    public final String code;
    public GradingFailure(int status,String code) { super(code); this.status=status; this.code=code; }
}
