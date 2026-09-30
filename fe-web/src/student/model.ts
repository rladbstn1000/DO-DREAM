export type Identity = { userId: number; name: string; role: 'TEACHER' | 'STUDENT'; demo: boolean };
export type StudentIndex = { state: string; readable: boolean; activeCurrent: boolean; sourceRevision: number };
export type Material = { materialId: number; materialTitle: string; teacherName: string; indexing: StudentIndex | null };
export type Chapter = { id: string; title: string; text: string };
export type Question = { id: number; version: number; content: string; question_number: number; title: string };
export type Mode = { environment: string; answer_provider: string; embedding_provider: string; grading_provider: string };
export type Source = { document_id: string; source_revision: number; source_hash: string; chunk_position: number;
  content_hash: string; material_title: string; excerpt: string };
export type ChatMessage = { id: number; role: string; content: string; sources?: Source[]; mode?: Mode; document_id?: string };
export const positiveId = (value: unknown): value is number => Number.isSafeInteger(value) && Number(value) > 0;
export const revision = (value: unknown): value is number => Number.isSafeInteger(value) && Number(value) >= 0;
export const canonicalId = (value: string | undefined) => value && /^[1-9][0-9]*$/.test(value) && Number.isSafeInteger(Number(value)) ? Number(value) : null;
export const isUuid = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value);
export function identity(value: unknown): Identity {
  const d = value as Identity;
  if (!d || !positiveId(d.userId) || typeof d.name !== 'string' || !['TEACHER', 'STUDENT'].includes(d.role) || typeof d.demo !== 'boolean') throw new Error('사용자 정보를 확인하지 못했습니다.');
  return { userId: d.userId, name: d.name, role: d.role, demo: d.demo };
}
export function studentIndex(value: unknown): StudentIndex | null {
  const d = value as StudentIndex;
  return d && ['NONE', 'QUEUED', 'PROCESSING', 'SUCCEEDED', 'FAILED', 'SUPERSEDED', 'REVOKED'].includes(d.state) &&
    typeof d.readable === 'boolean' && typeof d.activeCurrent === 'boolean' && revision(d.sourceRevision) &&
    (!d.activeCurrent || d.readable) ? { state: d.state, readable: d.readable, activeCurrent: d.activeCurrent, sourceRevision: d.sourceRevision } : null;
}
export function materials(value: unknown): Material[] {
  const list = (value as { materials?: unknown })?.materials;
  if (!Array.isArray(list)) throw new Error('자료 목록을 확인하지 못했습니다.');
  return list.map(d => {
    if (!positiveId(d.materialId) || typeof d.materialTitle !== 'string' || typeof d.teacherName !== 'string') throw new Error('자료 목록 형식이 올바르지 않습니다.');
    return { materialId: d.materialId, materialTitle: d.materialTitle, teacherName: d.teacherName, indexing: studentIndex(d.indexing) };
  });
}

/** Never create a DOM from server HTML. Output is rendered only as React text. */
export function plainText(value: unknown): string {
  if (typeof value !== 'string') return '';
  const text = value.slice(0, 200000).replace(/<(script|style|iframe|object|svg)\b[^>]*>[\s\S]*?<\/\1\s*>/gi, '')
    .replace(/<(br|\/p|\/div|\/li|\/h[1-6])\b[^>]*>/gi, '\n').replace(/<[^>]*>/g, '');
  return text.replace(/&(#x[0-9a-f]+|#[0-9]+|amp|lt|gt|quot|apos|nbsp);/gi, (whole, entity: string) => {
    const named: Record<string, string> = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' };
    if (!entity.startsWith('#')) return named[entity.toLowerCase()] ?? whole;
    const code = entity[1].toLowerCase() === 'x' ? parseInt(entity.slice(2), 16) : Number(entity.slice(1));
    return code > 0 && code <= 0x10ffff && !(code >= 0xd800 && code <= 0xdfff) ? String.fromCodePoint(code) : '';
  }).replace(/\n{3,}/g, '\n\n').trim();
}
export function chapters(value: unknown): Chapter[] {
  const list = (value as { chapters?: unknown })?.chapters;
  if (!Array.isArray(list)) throw new Error('본문을 확인하지 못했습니다.');
  return list.filter(d => d?.type === 'content').map((d, index) => {
    if (typeof d.title !== 'string' || typeof d.content !== 'string') throw new Error('본문 형식이 올바르지 않습니다.');
    return { id: typeof d.id === 'string' ? d.id : String(index + 1), title: plainText(d.title), text: plainText(d.content) };
  });
}
export function questions(value: unknown): Question[] {
  if (!Array.isArray(value) || value.length > 50) throw new Error('퀴즈를 확인하지 못했습니다.');
  return value.map(d => {
    if (!positiveId(d.id) || !revision(d.version) || typeof d.content !== 'string' || !positiveId(d.question_number)) throw new Error('문제 버전을 확인하지 못했습니다.');
    return { id: d.id, version: d.version, content: plainText(d.content), question_number: d.question_number, title: plainText(d.title) };
  });
}
export function source(value: unknown, materialId: number): Source {
  const d = value as Source;
  if (!d || String(d.document_id) !== String(materialId) || !revision(d.source_revision) || !revision(d.chunk_position) ||
    typeof d.source_hash !== 'string' || !/^[a-f0-9]{64}$/.test(d.source_hash) || typeof d.content_hash !== 'string' || !/^[a-f0-9]{64}$/.test(d.content_hash) ||
    typeof d.material_title !== 'string' || typeof d.excerpt !== 'string' || d.excerpt.length > 4000) throw new Error('참고 자료 정보를 확인하지 못했습니다.');
  return { document_id: String(d.document_id), source_revision: d.source_revision, source_hash: d.source_hash, chunk_position: d.chunk_position,
    content_hash: d.content_hash, material_title: d.material_title, excerpt: d.excerpt };
}
export function modeLabel(mode?: Mode | null) {
  if (mode?.answer_provider === 'local_stub' && mode.embedding_provider === 'local_hash8') return '로컬 대역 답변 · 8차원 로컬 임베딩 · 실제 자료 검색';
  return '실행 모드 확인 필요 · 실제 AI 품질은 검증하지 않았습니다';
}
export function readiness(value: StudentIndex | null) {
  if (!value) return '준비 상태 확인 필요';
  if (value.readable) return value.state === 'FAILED' ? '사용 가능 · 재색인 실패' : '사용 가능';
  if (value.state === 'FAILED') return '색인 실패';
  if (value.state === 'QUEUED') return '발행 접수';
  if (value.state === 'PROCESSING') return '색인 준비 중';
  return '아직 사용할 수 없음';
}
