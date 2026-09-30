/** Real Chrome UI journey. Fixture/negative API checks and injected delivery faults are labelled separately. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const directory = path.join(root, '.local/phase4/browser-ui');
const planPath = path.resolve(process.env.DODREAM_STUDENT_BROWSER_PLAN || '');
assert.equal(path.dirname(planPath), directory);
const plan = JSON.parse(await fs.readFile(planPath, 'utf8'));
assert.match(plan.runId, /^[a-f0-9-]{36}$/);
const origin = 'http://127.0.0.1:15173';
const resultsDir = path.join(root, '.local/phase4/results');
const screenshots = path.join(directory, plan.runId + '.screenshots');
await fs.mkdir(screenshots, { recursive: true });
const settings = Object.fromEntries((await fs.readFile(path.join(root, '.local/env'), 'utf8')).split('\n')
  .filter(line => line && !line.startsWith('#')).map(line => { const at=line.indexOf('='); return [line.slice(0,at),line.slice(at+1)]; }));
let playwright;
try { playwright=require('playwright'); } catch { playwright=require('/Users/yoonsu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'); }
const checks=[], logicalSubmissions=[], sourceEvidence=[];
let browser, step='launch', blockedExternal=0, seq=0, keyboardFocusChecks=0, category='ACTUAL_UI';
process.once('SIGTERM',async()=>{await browser?.close();process.exit(143);});
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function check(name, passed, detail={}) {
  const row={name,status:passed?'PASS':'FAIL',category,detail};checks.push(row);console.log(JSON.stringify(row));
  if(!passed){const error=new Error('Recorded check');error.recorded=true;throw error;}
}
async function context(base=origin) {
  const context=await browser.newContext({viewport:{width:1280,height:960},serviceWorkers:'block'});
  await context.route('**/*',route=>{
    if(new URL(route.request().url()).origin!==base){blockedExternal++;return route.abort();}
    return route.continue();
  });
  // Observe real events without replacing speech engines or voices.
  await context.addInitScript(()=>{
    window.__speechEvents=[];
    if(window.speechSynthesis){
      const speak=window.speechSynthesis.speak.bind(window.speechSynthesis);
      window.speechSynthesis.speak=utterance=>{
        for(const kind of ['start','end','error','pause','resume']) utterance.addEventListener(kind,()=>window.__speechEvents.push(kind));
        return speak(utterance);
      };
    }
  });
  const page=await context.newPage();page.setDefaultTimeout(20000);
  return {context,page,base};
}
async function api(page,pathname,method='GET',body) {
  assert.ok(pathname.startsWith('/api/')||pathname.startsWith('/ai/'));
  return page.evaluate(async({pathname,method,body})=>{
    const response=await fetch(pathname,{method,credentials:'include',signal:AbortSignal.timeout(30000),
      headers:{'Content-Type':'application/json',Authorization:'Bearer '+localStorage.getItem('accessToken')},
      body:body===undefined?undefined:JSON.stringify(body)});
    return {status:response.status,data:await response.json().catch(()=>null)};
  },{pathname,method,body});
}
async function keyboardTo(page,locator,activate=true) {
  await locator.waitFor({state:'visible'});
  for(let i=0;i<100;i++){
    if(await locator.evaluate(el=>el===document.activeElement)){
      assert.ok(await locator.evaluate(el=>getComputedStyle(el).outlineStyle!=='none'));
      keyboardFocusChecks++;
      if(activate)await page.keyboard.press('Enter');return;
    }
    await page.keyboard.press('Tab');
  }
  throw new Error('Keyboard target unreachable');
}
async function action(page,locator,keyboard=false){if(keyboard)await keyboardTo(page,locator);else await locator.click();}
async function fill(page,locator,value,keyboard=false){if(keyboard){await keyboardTo(page,locator,false);await page.keyboard.type(value);}else await locator.fill(value);}
async function start(state,keyboard=false){
  await state.page.goto(state.base+'/demo');
  await action(state.page,state.page.getByRole('button',{name:'학생 체험 시작',exact:true}),keyboard);
  await state.page.waitForURL('**/learn');
  await state.page.getByRole('heading',{name:'나의 자료함'}).waitFor();
  const identity=await api(state.page,'/api/session/me');assert.equal(identity.status,200);
  assert.equal(identity.data.role,'STUDENT');assert.equal(identity.data.demo,true);
  state.user=identity.data;return state;
}
async function teacherLogin(){
  const state=await context();const page=state.page;
  await page.goto(origin);await page.getByText('로그인 하기',{exact:true}).click();
  await page.locator('form.sign-in input[name="email"]').fill(plan.teacherEmail);
  await page.locator('form.sign-in input[name="password"]').fill(settings.LOCAL_TEACHER_PASSWORD);
  const login=page.waitForResponse(r=>r.url().endsWith('/api/auth/teacher/login'));
  await page.locator('form.sign-in button[type="submit"]').click();assert.equal((await login).status(),200);
  await page.waitForURL('**/classrooms');await page.locator('.swal2-container').waitFor({state:'hidden'});
  return state;
}
async function question(state,text,keyboard=false){
  await fill(state.page,state.page.getByLabel('질문',{exact:true}),text,keyboard);
  const response=state.page.waitForResponse(r=>r.url().endsWith('/ai/rag/chat')&&r.request().method()==='POST');
  await action(state.page,state.page.getByRole('button',{name:'질문 보내기',exact:true}),keyboard);
  return response;
}
async function journey(state,sample,teacher,keyboard=false){
  const page=state.page;
  await action(page,page.getByRole('link',{name:sample.title+' 학습 시작',exact:true}),keyboard);
  await page.getByRole('heading',{name:sample.title,exact:true}).waitFor();
  await action(page,page.getByRole('button',{name:'다음 단원',exact:true}),keyboard);
  check((keyboard?'keyboard':'pointer')+'_chapter_navigation',new URL(page.url()).searchParams.get('chapter')==='2');
  // The reader intentionally lands focus on the new chapter in rAF. Observe that
  // real landing before sending the next Tab; do not race it or force focus.
  if(keyboard)await page.waitForFunction(()=>document.querySelector('.learn-reading h2')===document.activeElement);
  const response=await question(state,'글에서 배운 내용을 알려 주세요.',keyboard);
  assert.equal(response.status(),200);const chat=await response.json();
  check((keyboard?'keyboard':'pointer')+'_real_answer_and_sources',chat.sources.length>0&&chat.mode.answer_provider==='local_stub'&&
    chat.sources.every(s=>s.source_revision===chat.source_revision&&s.source_hash===chat.source_hash));
  sourceEvidence.push(...chat.sources);state.chat=chat;
  await page.getByRole('button',{name:'참고 자료 보기',exact:true}).last().waitFor();
  if(!keyboard)await page.screenshot({path:path.join(screenshots,'learning-page.png'),fullPage:true});
  const sourceRead=page.waitForResponse(r=>r.url().includes(`/messages/${chat.message_id}/sources/0`));
  await action(page,page.getByRole('button',{name:'참고 자료 보기',exact:true}).last(),keyboard);
  assert.equal((await sourceRead).status(),200);
  await page.getByRole('dialog').waitFor();
  check((keyboard?'keyboard':'pointer')+'_same_version_source_dialog',(await page.getByRole('dialog').innerText()).includes(chat.sources[0].excerpt));
  if(!keyboard)await page.screenshot({path:path.join(screenshots,'source-reference.png')});
  await action(page,page.getByRole('button',{name:'참고 자료 닫기'}),keyboard);
  await action(page,page.getByRole('link',{name:'퀴즈 풀기',exact:true}),keyboard);
  const quizzes=await api(teacher.page,`/api/materials/${sample.materialId}/quizzes`);assert.equal(quizzes.status,200);
  for(let i=0;i<quizzes.data.length;i++)await fill(page,page.getByLabel(`문제 ${i+1} 답안`,{exact:true}),quizzes.data[i].correct_answer,keyboard);
  const submissions=[];
  const listener=request=>{if(request.url().endsWith(`/api/materials/${sample.materialId}/quizzes/submit`))submissions.push(request.headers()['idempotency-key']);};
  page.on('request',listener);
  if(keyboard)await action(page,page.getByRole('button',{name:'제출하기',exact:true}),true);
  else await page.getByRole('button',{name:'제출하기',exact:true}).click({clickCount:2});
  await page.waitForURL(new RegExp(`/learn/${sample.materialId}/results/[a-f0-9-]{36}$`));
  await page.getByRole('heading',{name:'퀴즈 결과',exact:true}).waitFor();
  await page.getByRole('region',{name:'채점 요약'}).waitFor();
  await page.waitForFunction(()=>document.querySelector('.learn-mode')?.textContent?.startsWith('로컬 대역 채점'));
  const attemptId=page.url().split('/').pop();
  check((keyboard?'keyboard':'pointer')+'_one_frozen_key_and_result',submissions.length>=1&&new Set(submissions).size===1);
  logicalSubmissions.push({userId:state.user.userId,materialId:sample.materialId,key:submissions[0],attemptId,questionCount:quizzes.data.length});
  state.attempt=attemptId;
  const text=await page.locator('main').innerText();
  await page.reload();await page.getByRole('heading',{name:'퀴즈 결과',exact:true}).waitFor();
  await page.getByRole('region',{name:'채점 요약'}).waitFor();
  await page.waitForFunction(()=>document.querySelector('.learn-mode')?.textContent?.startsWith('로컬 대역 채점'));
  check((keyboard?'keyboard':'pointer')+'_reload_same_snapshot',page.url().endsWith(attemptId)&&await page.locator('main').innerText()===text);
  check((keyboard?'keyboard':'pointer')+'_completed_pending_cleared',await page.evaluate(()=>!Object.keys(sessionStorage).some(k=>k.startsWith('dodream.student.pending.'))));
  if(!keyboard)await page.screenshot({path:path.join(screenshots,'quiz-result.png'),fullPage:true});
  page.off('request',listener);
}
async function event(name,evidence){
  const file=path.join(directory,`${plan.runId}.${++seq}.${name}`);
  await fs.writeFile(file+'.request.json',JSON.stringify({runId:plan.runId,event:name,evidence}),{flag:'wx'});
  for(let i=0;i<1200;i++){
    try{const result=JSON.parse(await fs.readFile(file+'.response.json','utf8'));assert.equal(result.status,'PASS');return;}catch(error){if(error.code!=='ENOENT')throw error;}
    await pause(100);
  }
  throw new Error('Owned fault checkpoint timeout');
}
const share=(teacher,mid,uid)=>api(teacher.page,'/api/materials/share','POST',{
  materialId:mid,shares:{[plan.classroomId]:{type:'INDIVIDUAL',studentIds:[uid]}}});
const revoke=(teacher,mid,uid)=>api(teacher.page,`/api/materials/${mid}/shares/${uid}`,'DELETE');
async function waitIndex(teacher,mid){
  for(let i=0;i<100;i++){
    const r=await api(teacher.page,`/api/documents/${mid}/indexing`);assert.equal(r.status,200);
    if(r.data.activeCurrent&&r.data.readable)return r.data;
    assert.ok(['QUEUED','PROCESSING'].includes(r.data.state));await pause(500);
  }throw new Error('Current index deadline');
}
let a,b,teacher,tts={apiEvents:[],audible:'NOT_RUN',voiceOver:'NOT_RUN'};
try{
  browser=await playwright.chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,
    args:['--disable-background-networking','--disable-component-update','--disable-sync','--no-first-run']});
  const sample=plan.samples[0];
  step='initial actual teacher login and first end-to-end student journey';
  teacher=await teacherLogin();a=await start(await context());
  await a.page.screenshot({path:path.join(screenshots,'library-desktop.png'),fullPage:true});
  await journey(a,sample,teacher);
  step='teacher observes the actual synthetic student result';
  await teacher.page.reload();
  await teacher.page.locator('.cl-classroom-card').filter({hasText:'3학년'}).first().click();
  await teacher.page.locator('.cl-student-card').filter({has:teacher.page.getByRole('heading',{name:a.user.name,exact:true})}).click();
  const resultCard=teacher.page.locator('.sr-quiz-card').filter({hasText:sample.title});
  await resultCard.waitFor();
  check('teacher_actual_result_card',/2개 정답/.test(await resultCard.innerText()),{studentId:a.user.userId});
  step='second independent visitor keyboard journey';
  b=await start(await context(),true);await journey(b,sample,teacher,true);
  check('keyboard_visible_focus_through_core_flow',keyboardFocusChecks>=9,{focusedControls:keyboardFocusChecks});
  check('independent_visitor_ids',a.user.userId!==b.user.userId);
  await event('verify-evidence',{logicalSubmissions,sourceEvidence});
  check('actual_database_and_chroma_match',true,{logicalSubmissions:logicalSubmissions.length,sources:sourceEvidence.length});
  category='ACTUAL_API_BOUNDARY';step='cross-user and role rejection with positive controls';
  for(const suffix of [`/api/materials/${sample.materialId}/quiz-attempts/${a.attempt}`,
    `/ai/rag/chat/sessions/${a.chat.session_id}/messages?student_id=${b.user.userId}`,
    `/ai/rag/chat/sessions/${a.chat.session_id}/messages/${a.chat.message_id}/sources/0?student_id=${b.user.userId}`])
    check('other_user_object_404',(await api(b.page,suffix)).status===404,{pathKind:suffix.includes('/sources/')?'source':suffix.includes('quiz-attempts')?'attempt':'session'});
  check('student_teacher_api_denied',(await api(b.page,'/api/documents/published')).status===403);
  category='ACTUAL_UI';await b.page.goto(origin+`/learn/${sample.materialId}/results/${a.attempt}`);
  await b.page.getByRole('alert').waitFor();check('other_attempt_direct_url_denied',!(await b.page.locator('main').innerText()).includes('2개 정답'));
  await b.page.goto(origin+'/classrooms');await b.page.waitForURL('**/learn');check('teacher_route_role_guard',true);
  step='narrow 320 CSS px reading and local speech API';
  await a.page.goto(origin+`/learn/${sample.materialId}`);await a.page.getByLabel('질문',{exact:true}).waitFor();
  await a.page.setViewportSize({width:320,height:900});
  check('320_css_px_no_horizontal_overflow',await a.page.evaluate(()=>document.documentElement.scrollWidth<=320));
  check('320_css_px_controls_not_clipped',await a.page.evaluate(()=>[...document.querySelectorAll('.learn-app button,.learn-app a,.learn-app textarea,.learn-reading-text')]
    .filter(el=>el.getClientRects().length&&el.getBoundingClientRect().top>=0).every(el=>{const r=el.getBoundingClientRect();return r.left>=0&&r.right<=320.5;})));
  // Capture the actual narrow viewport: full-page capture can repeat compositor
  // tiles when Chrome expands a 320px surface. Keep the readable body in view.
  await a.page.locator('.learn-reading').scrollIntoViewIfNeeded();
  await a.page.screenshot({path:path.join(screenshots,'learning-320.png')});
  await a.page.setViewportSize({width:1280,height:960});
  const voice=await a.page.evaluate(()=>window.speechSynthesis?.getVoices().some(v=>v.localService&&/^ko(?:-|_)/i.test(v.lang))||false);
  tts.localKoreanVoiceAvailable=voice;
  if(voice){await a.page.getByRole('button',{name:'본문 듣기',exact:true}).click();await pause(1500);
    tts.apiEvents=await a.page.evaluate(()=>window.__speechEvents);
    const stop=a.page.getByRole('button',{name:'듣기 중지',exact:true});if(await stop.isEnabled())await stop.click();
    check('tts_real_browser_event_observed',tts.apiEvents.length>0,{events:tts.apiEvents});
  }else{check('tts_local_voice_unavailable_guidance',await a.page.getByRole('button',{name:'본문 듣기',exact:true}).isDisabled());}
  step='real share revocation and source refusal';
  await a.page.getByRole('button',{name:'대화 기록 확인'}).click();await a.page.getByRole('button',{name:'참고 자료 보기',exact:true}).first().waitFor();
  assert.equal((await revoke(teacher,sample.materialId,a.user.userId)).status,204);
  try{
    await a.page.getByRole('button',{name:'참고 자료 보기',exact:true}).first().click();
    await a.page.getByRole('alert').waitFor();check('revoke_clears_visible_cached_material',await a.page.locator('.learn-reading').count()===0);
    category='ACTUAL_API_BOUNDARY';check('revoke_body_api_404',(await api(a.page,`/api/materials/shared/${sample.materialId}/json`)).status===404);
    check('revoke_source_api_404',(await api(a.page,`/ai/rag/chat/sessions/${a.chat.session_id}/messages/${a.chat.message_id}/sources/0?student_id=${a.user.userId}`)).status===404);
  }finally{assert.equal((await share(teacher,sample.materialId,a.user.userId)).status,200);}
  category='ACTUAL_UI';step='empty material list with actual revoked synthetic shares';
  try{
    for(const s of plan.samples)assert.equal((await revoke(teacher,s.materialId,b.user.userId)).status,204);
    await b.page.goto(origin+'/learn');await b.page.getByRole('heading',{name:'아직 공유받은 자료가 없어요'}).waitFor();check('empty_list_distinct',true);
    await b.page.goto(origin+`/learn/${sample.materialId}`);await b.page.getByRole('alert').waitFor();check('unshared_material_direct_url_denied',true);
  }finally{for(const s of plan.samples)assert.equal((await share(teacher,s.materialId,b.user.userId)).status,200);}
  step='quiz version change before submit and explicit recovery';
  await a.page.goto(origin+`/learn/${sample.materialId}/quiz`);await a.page.getByLabel('문제 1 답안',{exact:true}).fill('얼음');
  await a.page.getByLabel('문제 2 답안',{exact:true}).fill('증발');
  const oldQuizzes=(await api(teacher.page,`/api/materials/${sample.materialId}/quizzes`)).data;
  const changed=structuredClone(oldQuizzes);changed[0].content+=' (새 버전 확인)';
  try{
    assert.equal((await api(teacher.page,`/api/materials/${sample.materialId}/quizzes`,'POST',changed)).status,200);
    const conflict=a.page.waitForResponse(r=>r.url().endsWith('/quizzes/submit'));
    await a.page.getByRole('button',{name:'제출하기',exact:true}).click();assert.equal((await conflict).status(),409);
    await a.page.getByRole('alert').waitFor();check('quiz_version_conflict_explained',/문제.*변경|새.*문제/.test(await a.page.locator('main').innerText()));
  }finally{assert.equal((await api(teacher.page,`/api/materials/${sample.materialId}/quizzes`,'POST',oldQuizzes)).status,200);}
  // The remaining cases are separate real-server faults or explicitly identified response injections.
  const extra=await import('./browser-student-boundaries.mjs');
  await extra.runBoundaries({a,b,teacher,plan,origin,screenshots,api,check,setStep:value=>{step=value;},
    setCategory:value=>{category=value;},event,question,waitIndex,pause,start,context,logicalSubmissions,sourceEvidence});
  category='ACTUAL_UI';step='final healthy student flow after fault cleanup';
  await a.page.goto(origin+'/learn');await a.page.getByRole('link',{name:sample.title+' 학습 시작',exact:true}).waitFor();
  check('final_samples_available',await a.page.getByRole('link',{name:/학습 시작$/}).count()===2);
  check('no_external_resource_requests',blockedExternal===0,{blockedExternal});
}catch(error){
  if(!error.recorded){const row={name:'student_browser_execution',status:browser?'FAIL':'BLOCKED',category,detail:{step,errorType:error.name,assertionActual:['number','boolean'].includes(typeof error.actual)?error.actual:undefined,assertionExpected:['number','boolean'].includes(typeof error.expected)?error.expected:undefined,locations:(error.stack||'').split('\n').flatMap(line=>{const match=line.match(/(?:browser-student(?:-boundaries)?\.mjs):(\d+):(\d+)/);return match?[match[0]]:[];})}};checks.push(row);console.log(JSON.stringify(row));}
}finally{
  const version=browser?.version();if(browser)await browser.close();
  const report={runId:plan.runId,browser:'Chrome '+version,origin,mode:'ACTUAL_UI_PLUS_LABELLED_BOUNDARIES',checks,logicalSubmissions,sourceEvidence,tts,
    screenshots,blockedExternal,counts:Object.fromEntries(['PASS','FAIL','BLOCKED'].map(s=>[s,checks.filter(c=>c.status===s).length]))};
  for(const name of ['student-browser-'+plan.runId+'.json','student-browser.json'])await fs.writeFile(path.join(resultsDir,name),JSON.stringify(report,null,2)+'\n');
  process.exitCode=checks.some(c=>c.status!=='PASS')?1:0;
}
