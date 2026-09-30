package A704.DODREAM.indexing;

import A704.DODREAM.material.dto.PublishRequest;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.*;

/** External objects are prepared before the short publication transaction. The ledger dispatches later. */
@Service
public class IndexingService {
    private final IndexingStore store;
    private final S3Client objects;
    private final IndexingLocalHooks hooks;
    private final String bucket;
    public IndexingService(IndexingStore store,S3Client objects,IndexingLocalHooks hooks,@Value("${aws.s3.bucket}") String bucket) {
        this.store=store; this.objects=objects; this.hooks=hooks; this.bucket=bucket;
    }
    public IndexingStore.Publication publish(long actor,long fileId,PublishRequest request) {
        var prepared=store.prepareFile(actor,fileId,request);
        if(prepared.jsonKey()==null) throw new IndexingFailure(409,"PDF_NOT_PARSED");
        var source=IndexingSource.material(request.getEditedJson());
        byte[] body=json(request.getEditedJson());
        String key=immutableKey(prepared),quizKey=null;
        List<Object> quizChapters=new ArrayList<>();
        Object chapters=request.getEditedJson().get("chapters");
        if(chapters instanceof List<?> list) for(Object value:list)
            if(value instanceof Map<?,?> map && "quiz".equals(map.get("type"))) quizChapters.add(value);
        hooks.boundary(fileId,prepared.synthetic());
        prepareObject(key,body);
        if(!quizChapters.isEmpty()) { quizKey=immutableKey(prepared); prepareObject(quizKey,json(Map.of("chapters",quizChapters))); }
        hooks.prepared(fileId,prepared.synthetic());
        var publication=store.publish(actor,fileId,request,key,quizKey,source);
        hooks.committed(fileId,prepared.synthetic());
        return publication;
    }
    public IndexingSummary request(long actor,String kind,long id,String spec) {
        String selected=IndexingSource.spec(spec);
        var prepared=store.prepareResource(actor,kind,id);
        if(prepared.jsonKey()==null) throw new IndexingFailure(409,"PDF_NOT_PARSED");
        hooks.boundary(prepared.id(),prepared.synthetic());
        byte[] source=read(prepared.jsonKey());
        var parsed=IndexingSource.parse(source);
        var snapshot=kind.equals("PDF")?IndexingSource.initial(parsed):IndexingSource.material(parsed);
        return store.request(actor,kind,id,prepared,snapshot,selected);
    }
    public IndexingSummary completeInitial(long actor,long fileId,Map<String,Object> parsedData) {
        var prepared=store.prepareFile(actor,fileId,null);
        var snapshot=IndexingSource.initial(IndexingSource.JSON.valueToTree(parsedData));
        String key=immutableKey(prepared);
        hooks.boundary(fileId,prepared.synthetic());
        prepareObject(key,json(parsedData));
        Object indexes=parsedData.get("indexes");
        String indexText=indexes instanceof List<?> list?String.join(",",list.stream().filter(String.class::isInstance).map(String.class::cast).toList()):null;
        hooks.prepared(fileId,prepared.synthetic());
        var summary=store.completeInitial(actor,fileId,key,snapshot,indexText);
        hooks.committed(fileId,prepared.synthetic());
        return summary;
    }
    private String immutableKey(IndexingStore.FileView file) {
        // A fresh UUID names every prepared object. Existing JSON is never overwritten by publication.
        String prefix="local-synthetic-fixtures".equals(bucket)?"local/synthetic/indexing/":"published-json/"+file.ownerId()+"/"+file.id()+"/";
        return prefix+UUID.randomUUID()+".json";
    }
    private void prepareObject(String key,byte[] bytes) {
        objects.putObject(PutObjectRequest.builder().bucket(bucket).key(key).contentType("application/json")
            .overrideConfiguration(config->config.putHeader("If-None-Match","*")).build(),RequestBody.fromBytes(bytes));
        byte[] stored=read(key);
        if(!Arrays.equals(bytes,stored)) throw new IndexingFailure(503,"INDEXING_OBJECT_HASH_MISMATCH");
    }
    private byte[] read(String key) {
        try(var stream=objects.getObject(GetObjectRequest.builder().bucket(bucket).key(key).build())) {
            byte[] bytes=stream.readNBytes(IndexingSource.MAX_BYTES+1);
            if(bytes.length>IndexingSource.MAX_BYTES) throw new IndexingFailure(413,"INDEXING_SOURCE_TOO_LARGE");
            return bytes;
        } catch(java.io.IOException failure) { throw new IndexingFailure(503,"INDEXING_OBJECT_UNAVAILABLE"); }
    }
    private static byte[] json(Object value) {
        try {
            byte[] bytes=IndexingSource.JSON.writeValueAsBytes(value);
            if(bytes.length>IndexingSource.MAX_BYTES) throw new IndexingFailure(413,"INDEXING_SOURCE_TOO_LARGE");
            return bytes;
        } catch(java.io.IOException failure) { throw IndexingSource.invalid(); }
    }
}
