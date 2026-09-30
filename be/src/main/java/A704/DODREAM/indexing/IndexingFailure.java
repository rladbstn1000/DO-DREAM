package A704.DODREAM.indexing;

public final class IndexingFailure extends RuntimeException {
    private final int status;
    private final String code;
    public IndexingFailure(int status, String code) { super(code); this.status=status; this.code=code; }
    public int status() { return status; }
    public String code() { return code; }
}
