import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { authSession } from '../auth/client';
import { AuthSessionError } from '../auth/session';
import { useStudentSession } from './Session';
import { LearningLayout, Notice, useFence } from './Layout';
import { apiBase, studentJson } from './api';
import { materials, readiness, type Material } from './model';

type DemoConfig = { enabled: boolean; ready: boolean; mode: string; fixtureVersion: string;
  samples: { key: string; title: string; description: string; source: string; version: string; readable: boolean }[] };
export function DemoPage() {
  const { user, loading, error: identityError, refresh } = useStudentSession();
  const [config, setConfig] = useState<DemoConfig | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [recover, setRecover] = useState(false);
  const flight = useRef(false);
  const navigate = useNavigate();
  const fence = useFence();
  useEffect(() => {
    const abort = new AbortController();
    let active = true;
    const timer = setTimeout(() => abort.abort(), 12000);
    fetch(`${apiBase}/api/auth/demo/config`, { credentials: 'include', signal: abort.signal }).then(async response => {
      const data = await response.json();
      if (!response.ok || typeof data.enabled !== 'boolean' || typeof data.ready !== 'boolean' || !Array.isArray(data.samples)) throw new Error();
      if (!abort.signal.aborted) setConfig(data);
    }).catch(() => { if (active) setError('체험 설정을 확인하지 못했습니다. 잠시 뒤 이 페이지를 다시 열어주세요.'); })
      .finally(() => clearTimeout(timer));
    return () => { active = false; clearTimeout(timer); abort.abort(); };
  }, []);
  async function start(recovery: boolean) {
    if (flight.current) return;
    flight.current = true; setBusy(true); setError('');
    const generation = fence.capture();
    try {
      await authSession.startStudentDemo(recovery);
      if (fence.current(generation)) { refresh(); navigate('/learn'); }
    } catch (cause) {
      if (!fence.current(generation)) return;
      const status = cause instanceof AuthSessionError ? cause.status : 0;
      setError(status === 429 ? '현재 체험 인원 한도에 도달했습니다. 잠시 뒤 다시 이용해주세요.' : status === 503 ?
        '샘플 자료를 준비하고 있습니다. 준비가 완료된 뒤 시작해주세요.' : status === 409 ?
        '이 브라우저에 진행 중인 로그인이 있습니다. 기존 체험 로그인을 확인해주세요.' :
        '로그인 응답을 확인하지 못했습니다. 새 계정을 만들기 전에 기존 체험 로그인을 확인해주세요.');
      setRecover(true);
    } finally { flight.current = false; if (fence.current(generation)) setBusy(false); }
  }
  return <LearningLayout title="배움의 문을 두드려요" subtitle="읽고, 궁금한 것을 묻고, 내 생각을 답해보세요.">
    <section className="learn-hero"><div><span className="learn-pill">STUDENT EXPERIENCE</span><h2>오늘은 무엇을 배워볼까요?</h2><p>짧은 글을 내 속도로 읽고, 글에서 찾은 참고 자료와 함께 질문해보세요. 퀴즈 결과는 제출한 당시의 문제로 다시 볼 수 있어요.</p>
      <p className="learn-small">독립된 로컬 체험 학생으로 시작합니다. 실제 학생 정보와 외부 AI 서비스를 사용하지 않습니다.</p></div><div className="learn-steps" aria-label="학습 순서"><span>01 읽기</span><span>02 질문하기</span><span>03 퀴즈 풀기</span></div></section>
    {loading && <Notice>현재 로그인 정보를 확인하고 있습니다.</Notice>}
    {identityError && <Notice error>현재 로그인을 확인하지 못했습니다. 계정을 바꾸기 전에 <button onClick={refresh}>로그인 다시 확인</button>을 눌러주세요.</Notice>}
    {user ? <section className="learn-card"><h2>이미 로그인되어 있어요</h2><p>{user.name}님의 {user.role === 'TEACHER' ? '교사' : '학생'} 계정을 유지합니다. 새 체험은 명시적으로 로그아웃한 뒤 시작할 수 있습니다.</p>
      <Link className="learn-primary" to={user.role === 'TEACHER' ? '/classrooms' : '/learn'}>{user.role === 'TEACHER' ? '교사 화면으로' : '자료함으로'}</Link></section> :
      <section className="learn-card"><h2>나만의 체험 시작</h2><p>{config?.enabled ? '서버에서 허용한 로컬 전용 학생 체험' : '체험 설정을 확인하고 있습니다.'}</p>
        {config && !config.enabled && <Notice>이 서버에서는 학생 체험이 비활성화되어 있습니다.</Notice>}
        {config?.enabled && !config.ready && <Notice>샘플 자료의 색인을 준비하고 있습니다. 준비 완료 후 이용할 수 있어요.</Notice>}
        <button className="learn-primary" disabled={!config?.enabled || !config.ready || loading || identityError || busy} onClick={() => void start(false)}>{busy ? '체험 로그인 확인 중…' : '학생 체험 시작'}</button>
        {recover && <button disabled={busy} onClick={() => void start(true)}>기존 체험 로그인 확인</button>}
      </section>}
    {error && <Notice error>{error}</Notice>}
    <section aria-label="체험 학습 자료" className="learn-grid">{config?.samples.map(sample => <article key={sample.key} className="learn-card"><span className="learn-eyebrow">직접 작성한 학습 자료</span><h2>{sample.title}</h2><p>{sample.description}</p><p className="learn-small">{sample.source}</p><span className="learn-pill">{sample.readable ? '사용 가능' : '색인 준비 중'}</span></article>)}</section>
  </LearningLayout>;
}
export function LibraryPage() {
  const [list, setList] = useState<Material[] | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setBusy(true); setError(''); setList(null);
    studentJson('/api/materials/shared', { signal: controller.signal }).then(data => { if (!controller.signal.aborted) setList(materials(data)); })
      .catch(() => { if (!controller.signal.aborted) setError('자료 목록을 불러오지 못했습니다. 공유 상태를 다시 확인해주세요.'); })
      .finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [version]);
  return <LearningLayout title="나의 자료함" subtitle="선생님이 현재 공유한 자료만 보여요. 준비된 자료부터 시작해보세요.">
    <div className="learn-section-row"><h2>함께 읽을 자료</h2><button disabled={busy} onClick={() => setVersion(v => v + 1)}>자료 목록 새로고침</button></div>
    {busy && <Notice>자료 목록을 불러오고 있습니다.</Notice>}{error && <Notice error>{error}</Notice>}
    {list?.length === 0 && <section className="learn-card"><h2>아직 공유받은 자료가 없어요</h2><p>선생님이 자료를 공유하면 이곳에 나타납니다.</p></section>}
    <div className="learn-grid">{list?.map((material, index) => <article key={material.materialId} className="learn-card learn-material"><span className="learn-number">{String(index + 1).padStart(2, '0')}</span><span className="learn-pill">{readiness(material.indexing)}</span><h2>{material.materialTitle}</h2><p>{material.teacherName} 선생님이 공유한 자료</p><p className="learn-small">본문 읽기 · 자료에 질문하기 · 퀴즈</p>
      {material.indexing?.readable ? <Link className="learn-primary" to={`/learn/${material.materialId}`} aria-label={`${material.materialTitle} 학습 시작`}>학습 시작</Link> : <button disabled>준비 완료 후 학습 가능</button>}</article>)}</div>
  </LearningLayout>;
}
