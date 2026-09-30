import test from 'node:test';
import assert from 'node:assert/strict';
import { createStudentSubmission, pendingKey, readPending, parseResults } from '../src/student/submission.ts';
const key='6fac9508-1d59-4f91-a7bd-9ce12f1b8fe8', attempt='9d9a09bf-091f-4cc5-a3d2-df2bdba62fb2';
const questions=[{id:23,version:0,question_number:1,title:'합성 문제',content:'최초 문제'}];
const answers=[{quizId:23,version:0,answer:'  합성 답안  '}];
const result=[{question_id:23,version:0,questionContent:'최초 문제',snapshotAvailable:true,is_correct:true,student_answer:'  합성 답안  ',correct_answer:'서버 정답',ai_feedback:'제출 뒤 피드백'}];
const success=()=>({status:200,data:result,attemptId:attempt,state:'SUCCEEDED'});
const state=(name:string,generation=1,retryable=false)=>({status:name==='FAILED'?502:name==='UNKNOWN'?503:name==='REVOKED'?409:202,data:{attemptId:attempt,state:name,generation,retryable}});
const memory=()=>{const map=new Map<string,string>();return {map,getItem:(k:string)=>map.get(k)??null,setItem:(k:string,v:string)=>{map.set(k,v)},removeItem:(k:string)=>{map.delete(k)}}};
function fixture(request:Parameters<typeof createStudentSubmission>[0]['request'],storage=memory()) {
 let epoch=0,keys=0; const client=createStudentSubmission({userId:4,materialId:7,questions,storage,getEpoch:()=>epoch,makeKey:()=>{keys++;return key},request,changed:()=>{},wait:async()=>{}});
 return {client,storage,keys:()=>keys,change:()=>epoch++};
}
test('double click freezes one tab record and exact request/key',async()=>{
 const sent:unknown[]=[];let done!:(v:ReturnType<typeof success>)=>void;
 const f=fixture(async(...args)=>{sent.push(args);return new Promise(r=>{done=r})}); const input=structuredClone(answers);
 const first=f.client.submit(input),second=f.client.submit(input); input[0].answer='changed';
 await Promise.resolve(); assert.equal(first,second);assert.equal(f.keys(),1);assert.equal(sent.length,1);
 assert.deepEqual(f.client.getPending()?.answers,answers); assert.equal(readPending(f.storage,4,7)?.key,key);
 done(success());assert.equal((await first).state,'SUCCEEDED');assert.equal(f.storage.getItem(pendingKey(4,7)),null);
});
test('response loss survives controller recreation and explicit replay uses same key and frozen answers',async()=>{
 const sent:unknown[]=[];const storage=memory();const a=fixture(async(...args)=>{sent.push(args);throw Error('lost')},storage);
 assert.equal((await a.client.submit(answers)).state,'UNKNOWN');a.client.dispose();
 const b=fixture(async(...args)=>{sent.push(args);return success()},storage);assert.equal(b.keys(),0);
 assert.equal((await b.client.check()).state,'SUCCEEDED');assert.deepEqual(sent[0],sent[1]);assert.equal(b.keys(),0);
});
test('known attempt recovery only GETs and polling is bounded at three',async()=>{
 const sent:unknown[][]=[];const f=fixture(async(...args)=>{sent.push(args);return state('PROCESSING')});
 assert.equal((await f.client.submit(answers)).state,'PROCESSING');assert.deepEqual(sent.map(x=>x[1]),['POST','GET','GET','GET']);
 f.client.dispose();const b=fixture(async(...args)=>{sent.push(args);return success()},f.storage);await b.client.check();assert.equal(sent.at(-1)?.[1],'GET');
});
test('UNKNOWN needs confirmation; retry generation is persisted before dispatch and reused after refresh',async()=>{
 const sent:unknown[][]=[];const f=fixture(async(...args)=>{sent.push(args);if(sent.length===1)return state('UNKNOWN',1,true);throw Error('lost retry')});
 await f.client.submit(answers);await f.client.retry(false);assert.equal(sent.length,1);await f.client.retry(true);
 assert.deepEqual(readPending(f.storage,4,7)?.retry,{expectedGeneration:1,confirmUnknown:true});f.client.dispose();
 const b=fixture(async(...args)=>{sent.push(args);return success()},f.storage);await b.client.check();assert.deepEqual(sent[1],sent[2]);
});
test('server generation limit is retained without automatic retry',async()=>{
 let calls=0;const f=fixture(async()=>state('FAILED',++calls,true));await f.client.submit(answers);await f.client.retry(false);await f.client.retry(false);await f.client.retry(false);
 assert.equal(calls,3);assert.equal(f.client.getView().retryable,false);
});
test('changing frozen answers does not allocate another key',async()=>{let calls=0;const f=fixture(async()=>{calls++;return state('UNKNOWN')});await f.client.submit(answers);assert.equal((await f.client.submit([{...answers[0],answer:'new'}])).state,'CONFLICT');assert.equal(calls,1);assert.equal(f.keys(),1)});
test('logout and disposal fence late results and further writes',async()=>{
 for(const action of ['change','dispose']) {let done!:(v:ReturnType<typeof success>)=>void,calls=0;const f=fixture(async()=>{calls++;return new Promise(r=>{done=r})});const run=f.client.submit(answers);await Promise.resolve();if(action==='change')f.change();else f.client.dispose();done(success());assert.equal((await run).state,'SESSION_CHANGED');assert.equal((await f.client.check()).state,'SESSION_CHANGED');assert.equal(calls,1)}
});
test('storage write failure blocks network submission rather than promise recovery',async()=>{let calls=0;const storage=memory();storage.setItem=()=>{throw Error('quota')};const f=fixture(async()=>{calls++;return success()},storage);assert.equal((await f.client.submit(answers)).state,'STORAGE_UNAVAILABLE');assert.equal(calls,0)});
test('storage removal failure warns and refuses reset/new logical key',async()=>{const storage=memory();storage.removeItem=()=>{throw Error('disabled')};const f=fixture(async()=>success(),storage);const view=await f.client.submit(answers);assert.equal(view.state,'SUCCEEDED');assert.equal(view.storageWarning,true);assert.equal(f.client.reset(),false)});
test('stored identity, material, uuid, duplicate ids and oversized records cannot forge recovery',()=>{
 for(const patch of [{userId:5},{materialId:8},{key:'invalid'},{answers:[...answers,...answers]},{retry:{expectedGeneration:4,confirmUnknown:true},attemptId:attempt}]) {
 const storage=memory();storage.setItem(pendingKey(4,7),JSON.stringify({schema:1,userId:4,materialId:7,key,answers,...patch}));assert.equal(readPending(storage,4,7),null);assert.equal(storage.map.size,0);
 }
});
test('another verified user cannot see tab submission',async()=>{const f=fixture(async()=>state('UNKNOWN'));await f.client.submit(answers);assert.equal(readPending(f.storage,5,7),null);assert.equal(readPending(f.storage,4,8),null)});
test('snapshot mismatches and malformed responses never render scores',async()=>{
 for(const data of [[],[{...result[0],version:1}],[{...result[0],snapshotAvailable:false}],[{...result[0],correct_answer:null}]]) {const f=fixture(async()=>({...success(),data}));const view=await f.client.submit(answers);assert.equal(view.state,'UNKNOWN');assert.equal(view.results,undefined)}
});
test('version conflict remains explicit; permission denial clears pending',async()=>{
 for(const [response,expected] of [[{status:409,data:{code:'QUIZ_VERSION_CONFLICT'}},'VERSION_CONFLICT'],[{status:404,data:{}},'REVOKED'],[state('REVOKED'),'REVOKED']] as const) {const f=fixture(async()=>response);assert.equal((await f.client.submit(answers)).state,expected);if(expected==='REVOKED')assert.equal(f.storage.map.size,0)}
});
test('timeout ignores late completion and only explicit replay rechecks',async()=>{
 let done!:(v:ReturnType<typeof success>)=>void;const client=createStudentSubmission({userId:4,materialId:7,questions,storage:memory(),getEpoch:()=>0,makeKey:()=>key,timeout:2,changed:()=>{},request:async()=>new Promise(r=>{done=r})});
 assert.equal((await client.submit(answers)).state,'UNKNOWN');done(success());await Promise.resolve();assert.equal(client.getView().state,'UNKNOWN');
});
test('legacy result keeps absence of snapshot instead of current question fallback',()=>{const parsed=parseResults([{...result[0],snapshotAvailable:false,questionContent:undefined,version:undefined}]);assert.equal(parsed[0].snapshotAvailable,false);assert.equal(parsed[0].questionContent,undefined)});

test('one transient pending read failure fails closed without deleting or replacing a prior logical key',async()=>{
 const storage=memory();storage.setItem(pendingKey(4,7),JSON.stringify({schema:1,userId:4,materialId:7,key,answers}));const original=storage.getItem;let first=true,calls=0;storage.getItem=k=>{if(first){first=false;throw Error('transient read')}return original(k)};
 const f=fixture(async()=>{calls++;return success()},storage);assert.equal(f.client.getView().state,'STORAGE_UNAVAILABLE');assert.equal((await f.client.submit(answers)).state,'STORAGE_UNAVAILABLE');assert.equal(calls,0);assert.equal(f.keys(),0);assert.equal(f.client.reset(),false);assert.equal(readPending(storage,4,7)?.key,key);
});
