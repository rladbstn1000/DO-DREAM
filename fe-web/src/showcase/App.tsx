import { useMemo, useRef, useState, useSyncExternalStore } from 'react';
import {
  Link,
  Navigate,
  Route,
  Routes,
  useNavigate,
  useParams,
  useSearchParams,
} from 'react-router-dom';
import { TeacherExperience, TeacherJoin } from './teacher/Teacher';
import { StudentExperience } from './student/StudentExperience';
import type { ShowcasePort } from './port';
import fontLicense from './assets/jalnan-LICENSE.txt?url';
export type { ShowcasePort } from './port';

export function ShowcaseApp({ port }: { port: ShowcasePort }) {
  const state = useSyncExternalStore(
    port.store.subscribe,
    port.store.getSnapshot,
  );
  const uiState = useSyncExternalStore(
    port.uiStore.subscribe,
    port.uiStore.getSnapshot,
  );
  const epoch = useRef(0);
  const livePort = useMemo(
    () => ({ ...port, getEpoch: () => epoch.current }),
    [port],
  );
  const [resetCount, setResetCount] = useState(0);
  const [message, setMessage] = useState('');
  const navigate = useNavigate();
  return (
    <div
      className={`showcase-host${state.notice || uiState.notice || message ? ' showcase-has-notice' : ''}`}
    >
      <a
        className="showcase-skip"
        href="#showcase-main"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById('showcase-main')?.focus();
        }}
      >
        본문으로 건너뛰기
      </a>
      <header className="showcase-toolbar">
        <Link to="/" className="showcase-home">
          DO:DREAM
        </Link>
        <span className="showcase-sample">샘플 체험</span>
        <nav aria-label="체험 전환">
          <Link to="/teacher">교사 웹</Link>
          <Link to="/app/library">학생 앱</Link>
          <button
            data-testid="reset-demo"
            onClick={() => {
              epoch.current++;
              port.store.reset();
              port.uiStore.reset();
              setResetCount((count) => count + 1);
              setMessage('현재 탭의 샘플 체험을 초기화했습니다.');
              navigate('/');
            }}
          >
            초기화
          </button>
          <details className="showcase-guide">
            <summary>안내</summary>
            <div>
              <strong>포트폴리오용 샘플 체험</strong>
              <p>
                팀 프로젝트의 교사 웹과 학생 앱 화면을 브라우저에서 둘러보세요.
                편집·질문·예시 채점 기록은 현재 탭에서만 공유됩니다. 새로고침
                후에도 이 탭의 기록을 이어갑니다.
              </p>
              <p>
                공개 샘플 2개와 미리 준비된 질문·답변·서술형 판정 규칙을
                사용합니다. 본문을 편집해도 준비된 답변과 판정 규칙은 바뀌지
                않습니다. 말하기 버튼은 예시 선택을 엽니다. 실제
                로그인·업로드·AI·마이크·서버 저장을 사용하지 않습니다.
              </p>
              <p>원본 팀 구현: 4c763af · 웹 이식 및 샘플 연결: 개인 개선</p>
              <a href={fontLicense} target="_blank" rel="noreferrer">
                여기어때 잘난체 저작권·이용 조건
              </a>
            </div>
          </details>
        </nav>
      </header>
      {(state.notice || uiState.notice || message) && (
        <div className="showcase-notice" role="status">
          {[
            ...new Set([state.notice, uiState.notice, message].filter(Boolean)),
          ].join(' ')}
        </div>
      )}
      <div id="showcase-main" className="showcase-content" tabIndex={-1}>
        <Routes key={resetCount}>
          <Route path="/" element={<TeacherJoin />} />
          <Route
            path="/teacher/*"
            element={
              <TeacherExperience
                port={livePort}
                state={state}
                uiState={uiState}
              />
            }
          />
          <Route
            path="/app/*"
            element={
              <StudentExperience
                port={livePort}
                state={state}
                uiStore={port.uiStore}
                uiState={uiState}
              />
            }
          />
          <Route
            path="/learn"
            element={<Navigate to="/app/library" replace />}
          />
          <Route
            path="/learn/:sampleId"
            element={<Legacy port={port} screen="player" />}
          />
          <Route
            path="/learn/:sampleId/quiz"
            element={<Legacy port={port} screen="quiz" />}
          />
          <Route
            path="/learn/:sampleId/results/:resultId"
            element={<LegacyResult port={port} />}
          />
          <Route
            path="*"
            element={
              <div className="showcase-missing">
                <h1>이 체험 화면을 찾을 수 없습니다.</h1>
                <Link to="/">처음으로 돌아가기</Link>
              </div>
            }
          />
        </Routes>
      </div>
    </div>
  );
}
function Legacy({ port, screen }: { port: ShowcasePort; screen: string }) {
  const { sampleId } = useParams();
  const [search] = useSearchParams();
  if (!port.findSample(sampleId))
    return (
      <div className="showcase-missing">
        <h1>샘플 교재를 찾을 수 없습니다.</h1>
        <Link to="/app/library">서재로 돌아가기</Link>
      </div>
    );
  return (
    <Navigate
      replace
      to={`/app/material/${sampleId}/${screen}${screen === 'player' ? `?${search}` : ''}`}
    />
  );
}
function LegacyResult({ port }: { port: ShowcasePort }) {
  const { sampleId, resultId } = useParams();
  const state = useSyncExternalStore(
    port.store.subscribe,
    port.store.getSnapshot,
  );
  const sample = port.findSample(sampleId);
  const result = sample
    ? state.samples[sample.id].results.find(
        (row) => `run-${row.attemptNumber}` === resultId,
      )
    : undefined;
  return (
    <div className="showcase-missing">
      <h1>이전 선택형 체험 기록</h1>
      <p>
        이 주소는 이전 공개 데모의 선택형 퀴즈 결과입니다. 새 학생 앱은 원본의
        서술형 퀴즈 흐름으로 연결됩니다.
      </p>
      {result ? (
        <p>
          {result.attemptNumber}회차 · {result.total}문제 중 {result.score}문제
          정답
        </p>
      ) : (
        <p>이 탭에 저장된 이전 결과가 없습니다.</p>
      )}
      <Link to="/app/library">학생 앱 서재로</Link>
    </div>
  );
}
