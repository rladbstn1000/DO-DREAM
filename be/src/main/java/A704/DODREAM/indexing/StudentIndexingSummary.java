package A704.DODREAM.indexing;

/** No job ID, retry capability, physical collection or source bytes in student metadata. */
public record StudentIndexingSummary(String state,boolean readable,boolean activeCurrent,long sourceRevision) {
    public static StudentIndexingSummary from(IndexingSummary value) {
        return new StudentIndexingSummary(value.state(),value.readable(),value.activeCurrent(),value.sourceRevision());
    }
}
