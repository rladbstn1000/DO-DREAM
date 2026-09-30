package A704.DODREAM.indexing;

/** Owner-safe status. Physical collection names, source bytes and delivery capabilities stay internal. */
public record IndexingSummary(String jobId,String state,long sourceRevision,boolean readable,
    boolean activeCurrent,boolean retryable,int executionGeneration) {
    public static IndexingSummary none() { return new IndexingSummary(null,"NONE",0,false,false,false,0); }
}
