/** Boundary coverage for the real student journey; injected responses are explicitly separated. */
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';

export async function runBoundaries(ctx) {
  const { a,b,teacher,plan,origin,api,check,setStep,setCategory,event,question,waitIndex,pause,start,context,
    logicalSubmissions,sourceEvidence }=ctx;
  const sample=plan.samples[0], mid=sample.materialId;
  const quizUrl=`${origin}/api/materials/${mid}/quizzes/submit`;
  const pending=page=>page.evaluate(()=>Object.keys(sessionStorage).filter(k=>k.startsWith('dodream.student.pending.'))
    .map(k=>JSON.parse(sessionStorage.getItem(k))));
  async function read(page) {
    await page.goto(`${origin}/learn/${mid}`);
    await page.getByLabel('질문',{exact:true}).waitFor();
  }
  async function questions() {
    const response=await api(teacher.page,`/api/materials/${mid}/quizzes`);
    assert.equal(response.status,200);assert.ok(Array.isArray(response.data)&&response.data.length>0);
    return response.data;
  }
  async function fillQuiz(page,items) {
    for(let i=0;i<items.length;i++)await page.getByLabel(`문제 ${i+1} 답안`,{exact:true}).fill(items[i].correct_answer);
  }
  async function assertHealthyIdentity(state) {
    const response=await api(state.page,'/api/session/me');
    assert.equal(response.status,200);assert.equal(response.data.userId,state.user.userId);
  }
  async function noExecutableMarkup(page,selector) {
    return page.evaluate(selector=>!window.__studentXss&&
      document.querySelectorAll(`${selector} script, ${selector} img, ${selector} iframe, ${selector} a[href^="javascript:"]`).length===0,selector);
  }

  setStep('lost successful grading delivery, reload and same frozen submission');
  setCategory('ACTUAL_SERVER_WITH_DELIVERY_FAULT');
  // The previous real version conflict has no accepted attempt. Its explicit UI
  // action obtains current questions and discards that rejected frozen request.
  await a.page.getByRole('button',{name:'최신 문제로 새 풀이 시작',exact:true}).click();
  const items=await questions();await fillQuiz(a.page,items);
  let lost;
  const keys=[];
  const record=request=>{if(request.url()===quizUrl&&request.method()==='POST')keys.push(request.headers()['idempotency-key']);};
  a.page.on('request',record);
  const drop=async route=>{
    const response=await route.fetch();
    assert.equal(response.status(),200);
    lost={attemptId:response.headers()['x-grading-attempt-id'],data:await response.json()};
    await route.abort('failed');
  };
  await a.page.route(quizUrl,drop,{times:1});
  try {
    await a.page.getByRole('button',{name:'제출하기',exact:true}).click();
    await a.page.locator('[data-grading-state="UNKNOWN"]').waitFor();
    assert.ok(lost?.attemptId);
    const stored=await pending(a.page);
    check('lost_delivery_keeps_frozen_pending',stored.length===1&&stored[0].userId===a.user.userId&&
      stored[0].materialId===mid&&stored[0].key===keys[0]&&!stored[0].attemptId);
    await a.page.reload();
    await a.page.getByRole('button',{name:'같은 제출 확인',exact:true}).waitFor();
    const restored=await pending(a.page);
    check('reload_preserves_same_frozen_body',JSON.stringify(restored)===JSON.stringify(stored));
    await a.page.getByRole('button',{name:'같은 제출 확인',exact:true}).click();
    await a.page.waitForURL(`**/learn/${mid}/results/${lost.attemptId}`);
    await a.page.getByRole('heading',{name:'퀴즈 결과',exact:true}).waitFor();
    check('lost_delivery_replay_same_key_attempt',keys.length===2&&new Set(keys).size===1&&
      (await pending(a.page)).length===0);
    logicalSubmissions.push({userId:a.user.userId,materialId:mid,key:keys[0],attemptId:lost.attemptId,questionCount:items.length});
    await event('verify-evidence',{logicalSubmissions,sourceEvidence:[sourceEvidence[0]]});
  } finally { await a.page.unroute(quizUrl,drop);a.page.off('request',record); }

  setStep('real publication changes source, queued UI, 409 and explicit new conversation');
  setCategory('ACTUAL_SERVER_WITH_OWN_SERVICE_FAULT');
  const originalResponse=await api(teacher.page,`/api/pdf/${sample.uploadedFileId}/json`);
  assert.equal(originalResponse.status,200);
  // The teacher wrapper contains parsedData; its published object is the
  // editedJson payload itself, with chapters directly at that level.
  const original=originalResponse.data?.parsedData;
  assert.ok(original?.chapters?.length);
  const originalQuizzes=await questions();
  const publication={materialTitle:sample.title,labelColor:'BLUE',
    editedJson:structuredClone(original),quizzes:originalQuizzes};
  const changed=structuredClone(publication);
  changed.editedJson.chapters[0].content+=' 이번 웹 체험에서는 자료가 새 버전으로 바뀌는 상황을 확인합니다.';
  await read(a.page);
  const previous=(await question(a,'현재 자료의 내용을 확인해 주세요.'));
  assert.equal(previous.status(),200);const previousChat=await previous.json();
  let dispatcherStopped=false,published=false;
  try {
    await event('dispatcher-stop');dispatcherStopped=true;
    const queued=await api(teacher.page,`/api/documents/${sample.uploadedFileId}/publish`,'POST',changed);
    assert.equal(queued.status,200);published=true;
    const status=await api(teacher.page,`/api/documents/${mid}/indexing`);
    assert.equal(status.status,200);
    check('changed_source_is_not_ready_on_acceptance',status.data.state==='QUEUED'&&!status.data.readable&&!status.data.activeCurrent);
    await b.page.goto(origin+'/learn');
    const card=b.page.locator('.learn-material').filter({has:b.page.getByRole('heading',{name:sample.title,exact:true})});
    await card.getByRole('button',{name:'준비 완료 후 학습 가능',exact:true}).waitFor();
    check('queued_library_start_is_disabled',await card.getByRole('button',{name:'준비 완료 후 학습 가능',exact:true}).isDisabled()&&
      await card.getByRole('link',{name:sample.title+' 학습 시작',exact:true}).count()===0);
    await event('dispatcher-start');dispatcherStopped=false;
    await waitIndex(teacher,mid);
    const conflict=await question(a,'이전 대화에서 계속 질문합니다.');
    assert.equal(conflict.status(),409);
    const conflictBody=await conflict.json();assert.equal(conflictBody.detail?.code,'RAG_SOURCE_CHANGED');
    await a.page.getByRole('button',{name:'새 자료로 대화 시작',exact:true}).waitFor();
    check('source_change_requires_explicit_new_conversation',await a.page.getByRole('button',{name:'질문 보내기',exact:true}).count()===0);
    await a.page.getByRole('button',{name:'새 자료로 대화 시작',exact:true}).click();
    const fresh=await question(a,'새 자료의 내용을 확인해 주세요.');assert.equal(fresh.status(),200);
    const chat=await fresh.json();
    check('new_conversation_uses_new_source_revision',chat.session_id!==previousChat.session_id&&
      chat.source_revision>previousChat.source_revision&&chat.source_hash!==previousChat.source_hash&&
      chat.sources.length>0&&chat.sources.every(s=>s.source_revision===chat.source_revision&&s.source_hash===chat.source_hash));
    sourceEvidence.push(...chat.sources);
    await event('verify-evidence',{logicalSubmissions,sourceEvidence:chat.sources});
    const oldHistory=await api(a.page,`/ai/rag/chat/sessions/${previousChat.session_id}/messages?student_id=${a.user.userId}`);
    check('old_conversation_retained',oldHistory.status===200&&oldHistory.data.messages.some(m=>m.id===previousChat.message_id));
  } finally {
    if(dispatcherStopped)await event('dispatcher-start');
    if(published){assert.equal((await api(teacher.page,`/api/documents/${sample.uploadedFileId}/publish`,'POST',publication)).status,200);await waitIndex(teacher,mid);}
  }

  setStep('actual Chroma outage produces a storage error without a fabricated answer');
  setCategory('ACTUAL_SERVER_WITH_OWN_SERVICE_FAULT');
  await read(a.page);
  // Its retained session belongs to the preceding version. Choose the new one
  // explicitly, before inducing the storage failure under test.
  const stale=await question(a,'복원된 자료로 대화를 시작합니다.');assert.equal(stale.status(),409);
  await a.page.getByRole('button',{name:'새 자료로 대화 시작',exact:true}).click();
  const baseline=await question(a,'저장소 장애 전 자료 내용을 확인합니다.');assert.equal(baseline.status(),200);
  const baselineChat=await baseline.json();
  const messagesBefore=await a.page.locator('.learn-message').count();
  await event('chroma-pause');
  try {
    const failed=await question(a,'저장소 장애 중 질문입니다.');assert.equal(failed.status(),503);
    const body=await failed.json();assert.equal(body.detail?.code,'INDEX_STORAGE_UNAVAILABLE');
    await a.page.getByRole('alert').filter({hasText:'자료 검색 저장소를 사용할 수 없습니다'}).waitFor();
    check('real_storage_failure_has_no_fake_answer',await a.page.locator('.learn-message').count()===messagesBefore);
  } finally { await event('chroma-unpause'); }
  const recovered=await question(a,'저장소 복구 후 다시 확인합니다.');assert.equal(recovered.status(),200);
  const recoveredChat=await recovered.json();
  check('storage_recovery_keeps_authorized_session',recoveredChat.session_id===baselineChat.session_id);
  await event('verify-evidence',{logicalSubmissions,sourceEvidence:recoveredChat.sources});

  setStep('short-lived access token expires and real student cookie refresh preserves identity');
  setCategory('ACTUAL_UI');
  const short=await start(await context('http://127.0.0.1:15174'));
  try {
    await pause(8000);
    const refreshed=short.page.waitForResponse(r=>r.url().endsWith('/api/auth/student/refresh')&&r.request().method()==='POST');
    await short.page.getByRole('button',{name:'자료 목록 새로고침',exact:true}).click();
    assert.equal((await refreshed).status(),200);
    await short.page.getByRole('link',{name:sample.title+' 학습 시작',exact:true}).waitFor();
    await assertHealthyIdentity(short);
    check('expired_student_access_cookie_refresh_same_identity',true,{studentId:short.user.userId});
    check('student_refresh_secrets_not_in_javascript',await short.page.evaluate(()=>
      !Object.keys(localStorage).some(k=>/refresh|device.?secret|bootstrap/i.test(k))&&
      !document.cookie.split(';').some(c=>/^\s*(refresh|dodream_demo_visitor)=/.test(c))));
    await short.page.getByRole('button',{name:'로그아웃',exact:true}).click();
    await short.page.waitForURL('**/demo');
  } finally { await short.context.close(); }

  setStep('explicit injected UNKNOWN state exposes confirmation without a zero score');
  setCategory('ERROR_RESPONSE_INJECTION');
  await b.page.goto(`${origin}/learn/${mid}/quiz`);await fillQuiz(b.page,await questions());
  const injectedAttempt=randomUUID();
  const unknown=route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({
    attemptId:injectedAttempt,state:'UNKNOWN',generation:1,retryable:true,failureCode:'TEST_RESPONSE_INJECTION'})});
  await b.page.route(quizUrl,unknown,{times:1});
  try {
    await b.page.getByRole('button',{name:'제출하기',exact:true}).click();
    await b.page.locator('[data-grading-state="UNKNOWN"]').waitFor();
    const confirm=b.page.getByLabel('이전 실행 결과가 불명임을 확인하고 같은 제출을 재시도합니다.',{exact:true});
    check('injected_unknown_is_not_a_score',await confirm.count()===1&&
      await b.page.getByRole('button',{name:'채점 재시도',exact:true}).isDisabled()&&
      await b.page.locator('.learn-result-summary').count()===0);
    await confirm.check();
    check('injected_unknown_retry_requires_confirmation',await b.page.getByRole('button',{name:'채점 재시도',exact:true}).isEnabled());
  } finally { await b.page.unroute(quizUrl,unknown); }

  setStep('logout fences a real delayed chat delivery and clears pending submission');
  setCategory('ACTUAL_SERVER_WITH_DELIVERY_FAULT');
  await read(b.page);
  // b's original session is stale after the real source restoration.
  const old=await question(b,'현재 자료로 돌아갑니다.');assert.equal(old.status(),409);
  await b.page.getByRole('button',{name:'새 자료로 대화 시작',exact:true}).click();
  let release,delivered,accepted;
  const barrier=new Promise(resolve=>{release=resolve;});
  const receipt=new Promise(resolve=>{accepted=resolve;});
  const deliveredPromise=new Promise(resolve=>{delivered=resolve;});
  const late=async route=>{
    try { const response=await route.fetch();assert.equal(response.status(),200);accepted();
      await barrier;await route.fulfill({response});
    } finally { delivered(); }
  };
  await b.page.route(origin+'/ai/rag/chat',late,{times:1});
  try {
    await b.page.getByLabel('질문',{exact:true}).fill('로그아웃 뒤에는 표시하지 않을 늦은 응답');
    await b.page.getByRole('button',{name:'질문 보내기',exact:true}).click();
    await Promise.race([receipt,pause(25000).then(()=>{throw new Error('Delayed server receipt deadline');})]);
    assert.equal((await pending(b.page)).length,1);
    await b.page.getByRole('button',{name:'로그아웃',exact:true}).click();
    await b.page.waitForURL('**/demo');release();await deliveredPromise;
    check('logout_clears_pending_and_blocks_late_content',(await pending(b.page)).length===0&&
      !(await b.page.locator('main').innerText()).includes('로그아웃 뒤에는 표시하지 않을 늦은 응답')&&
      await b.page.evaluate(()=>localStorage.getItem('accessToken')===null));
    await b.page.goto(`${origin}/learn/${mid}/quiz`);await b.page.waitForURL('**/demo');
    check('logged_out_direct_pending_recovery_blocked',await b.page.getByRole('button',{name:'같은 제출 확인',exact:true}).count()===0);
  } finally { release();await b.page.unroute(origin+'/ai/rag/chat',late); }
  await start(b); // same opaque visitor, explicit user action, no shared account.

  setStep('injected answer provider failure is explained and never replaced by success');
  setCategory('ERROR_RESPONSE_INJECTION');
  await read(b.page);
  const providerFailure=route=>route.fulfill({status:503,contentType:'application/json',
    body:JSON.stringify({detail:'RAG processing unavailable'})});
  await b.page.route(origin+'/ai/rag/chat',providerFailure,{times:1});
  try {
    assert.equal((await question(b,'답변 모델 오류 안내 확인')).status(),503);
    await b.page.getByRole('alert').filter({hasText:'답변 응답을 확인하지 못했습니다'}).waitFor();
    check('injected_provider_error_does_not_fabricate_answer',await b.page.locator('.learn-message').count()===0&&
      await b.page.getByRole('button',{name:'대화 기록 확인',exact:true}).isEnabled());
  } finally { await b.page.unroute(origin+'/ai/rag/chat',providerFailure); }

  setStep('injected dangerous markup remains text in student body, answer and source');
  setCategory('ERROR_RESPONSE_INJECTION');
  const marker='보안 렌더러 확인';
  const markup=`${marker}<script>window.__studentXss=1</script><img src="https://student-ui-security.invalid/image" onerror="window.__studentXss=1"><a href="javascript:window.__studentXss=1">링크</a>`;
  const bodyUrl=`${origin}/api/materials/shared/${mid}/json`;
  const maliciousBody=async route=>{const response=await route.fetch();assert.equal(response.status(),200);
    const data=await response.json();data.chapters[0].content=markup;
    await route.fulfill({response,json:data});};
  const maliciousChat=async route=>{const response=await route.fetch();assert.equal(response.status(),200);
    const data=await response.json();data.answer=markup;data.sources=data.sources.map(s=>({...s,excerpt:markup}));
    await route.fulfill({response,json:data});};
  const maliciousSource=async route=>{const response=await route.fetch();assert.equal(response.status(),200);
    const data=await response.json();data.excerpt=markup;await route.fulfill({response,json:data});};
  await b.page.route(bodyUrl,maliciousBody,{times:1});
  await b.page.route(origin+'/ai/rag/chat',maliciousChat,{times:1});
  await b.page.route('**/ai/rag/chat/sessions/*/messages/*/sources/*?*',maliciousSource,{times:1});
  try {
    await read(b.page);await b.page.locator('.learn-reading').getByText(marker,{exact:false}).waitFor();
    check('injected_body_html_not_executable',await noExecutableMarkup(b.page,'.learn-reading'));
    assert.equal((await question(b,'렌더러 안전 확인')).status(),200);
    await b.page.locator('.learn-message').filter({hasText:marker}).waitFor();
    check('injected_answer_html_is_text',await noExecutableMarkup(b.page,'.learn-conversation'));
    await b.page.getByRole('button',{name:'참고 자료 보기',exact:true}).last().click();
    await b.page.getByRole('dialog').waitFor();
    check('injected_source_html_is_text',(await b.page.getByRole('dialog').innerText()).includes(markup)&&
      await noExecutableMarkup(b.page,'.learn-source-dialog'));
    await b.page.getByRole('button',{name:'참고 자료 닫기',exact:true}).click();
  } finally {
    await b.page.unroute(bodyUrl,maliciousBody);await b.page.unroute(origin+'/ai/rag/chat',maliciousChat);
    await b.page.unroute('**/ai/rag/chat/sessions/*/messages/*/sources/*?*',maliciousSource);
  }
  setStep('unavailable tab storage blocks a new submission before sending it');
  setCategory('BROWSER_STORAGE_FAULT');
  await b.page.goto(`${origin}/learn/${mid}/quiz`);await fillQuiz(b.page,await questions());
  let forbiddenSubmissions=0;
  const observe=request=>{if(request.url()===quizUrl&&request.method()==='POST')forbiddenSubmissions++;};
  b.page.on('request',observe);
  await b.page.evaluate(()=>{
    const setItem=Storage.prototype.setItem;
    window.__restoreStudentStorage=()=>{Storage.prototype.setItem=setItem;};
    Storage.prototype.setItem=function(key,value){
      if(this===sessionStorage&&String(key).startsWith('dodream.student.pending.'))throw new DOMException('Synthetic unavailable tab storage','QuotaExceededError');
      return setItem.call(this,key,value);
    };
  });
  try {
    await b.page.getByRole('button',{name:'제출하기',exact:true}).click();
    await b.page.locator('[data-grading-state="STORAGE_UNAVAILABLE"]').waitFor();
    check('storage_failure_blocks_unrecoverable_submission',forbiddenSubmissions===0&&
      (await pending(b.page)).length===0&&/복구를 보장할 수 없습니다/.test(await b.page.locator('main').innerText()));
  } finally {
    await b.page.evaluate(()=>window.__restoreStudentStorage?.());b.page.off('request',observe);
  }
  setStep('disabled demo UI contract with an explicitly injected server configuration');
  setCategory('ERROR_RESPONSE_INJECTION');
  const disabled=await context();
  try {
    await disabled.page.route(origin+'/api/auth/demo/config',route=>route.fulfill({status:200,contentType:'application/json',
      body:JSON.stringify({enabled:false,ready:false,mode:'UNAVAILABLE',samples:[]})}),{times:1});
    await disabled.page.goto(origin+'/demo');
    await disabled.page.getByText('이 서버에서는 학생 체험이 비활성화되어 있습니다.',{exact:true}).waitFor();
    check('injected_disabled_config_blocks_ui_start',await disabled.page.getByRole('button',{name:'학생 체험 시작',exact:true}).isDisabled());
  } finally { await disabled.context.close(); }
  setCategory('ACTUAL_UI');
  await read(b.page);await assertHealthyIdentity(b);
}
