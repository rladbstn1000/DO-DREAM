import { useEffect, useRef, useState } from 'react';
import { authenticatedFetch, authSession } from '../auth/client';
import { createIndexingController, indexingPending, indexingPresentation, parseIndexingSummary } from '../indexing/status';
import type { IndexingView } from '../indexing/status';
import './IndexingStatus.css';

export default function IndexingStatus({ resourcePath, initial }: { resourcePath: string; initial?: unknown }) {
  const controller = useRef<ReturnType<typeof createIndexingController> | null>(null);
  const [view, setView] = useState<IndexingView>({ summary: parseIndexingSummary(initial), error: null, busy: false, exhausted: false });
  useEffect(() => {
    if (!/^\/api\/(documents|pdf)\/[1-9][0-9]*\/indexing$/.test(resourcePath)) {
      setView({ summary: null, error: 'unavailable', busy: false, exhausted: false });
      return;
    }
    const next = createIndexingController({ resourcePath, initial, getEpoch: authSession.getEpoch, changed: setView,
      request: async ({ method, path, body, signal }) => {
        const base = (import.meta.env.VITE_API_BASE || '').replace(/\/+$/, '');
        const response = await authenticatedFetch(base + path, { method, signal, credentials: 'include',
          headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
        const data = await response.json().catch(() => null);
        return { status: response.status, data };
      },
    });
    controller.current = next;
    setView(next.getView());
    if (!next.getView().summary || indexingPending(next.getView().summary)) void next.refresh();
    return () => { next.dispose(); if (controller.current === next) controller.current = null; };
  }, [resourcePath, initial]);
  const display = indexingPresentation(view);
  return <div className="indexing-status" data-indexing-resource={resourcePath} onClick={event => event.stopPropagation()}>
    <span className={`indexing-badge indexing-${display.tone}`} role="status" aria-live="polite" title={display.hint}>{display.label}</span>
    <button type="button" className="indexing-check" disabled={view.busy} onClick={() => { void controller.current?.refresh(); }}>
      {view.busy ? '상태 확인 중' : '상태 확인'}
    </button>
    {!view.error && view.summary?.retryable && <button type="button" className="indexing-check" disabled={view.busy}
      onClick={() => { void controller.current?.retry(); }}>색인 다시 시도</button>}
    {view.exhausted && <span className="indexing-note">준비가 계속되고 있습니다. 잠시 뒤 상태를 확인해주세요.</span>}
  </div>;
}
