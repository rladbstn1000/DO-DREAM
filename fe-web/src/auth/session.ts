type TokenResponse = { accessToken: string; teacherName?: string };
type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
type Options = {
  storage: StorageLike;
  fetch: typeof fetch;
  origin: string;
  apiBase?: string;
  ragBase?: string;
  onChange?: (authenticated: boolean, reason?: string) => void;
};

export class AuthSessionError extends Error {
  status: number;
  constructor(message: string, status = 401) {
    super(message);
    this.name = 'AuthSessionError';
    this.status = status;
  }
}

/** One browser tab owns one refresh flight. Tokens remain in the existing storage. */
export function createAuthSession(options: Options) {
  const apiBase = (options.apiBase || '').replace(/\/+$/, '');
  const ragBase = (options.ragBase || '/ai').replace(/\/+$/, '');
  const apiScope = new URL(`${apiBase}/api/`, options.origin);
  const ragScope = new URL(`${ragBase}/rag/`, options.origin);
  const inScope = (url: URL, scope: URL) => url.origin === scope.origin &&
    (url.pathname === scope.pathname.slice(0, -1) || url.pathname.startsWith(scope.pathname));
  let epoch = 0;
  let csrf: { token: string; headerName: string } | null = null;
  let csrfFlight: { epoch: number; promise: Promise<typeof csrf> } | null = null;
  let refreshFlight: { epoch: number; promise: Promise<string> } | null = null;
  const controllers = new Set<AbortController>();
  const token = () => options.storage.getItem('accessToken');
  const assertCurrent = (expected: number) => {
    if (epoch !== expected) throw new AuthSessionError('인증 상태가 변경되었습니다.');
  };
  const transition = (reason?: string) => {
    epoch += 1;
    for (const controller of controllers) controller.abort();
    controllers.clear();
    refreshFlight = null;
    csrfFlight = null;
    csrf = null;
    for (const key of ['accessToken', 'isLoggedIn', 'teacherName']) options.storage.removeItem(key);
    options.onChange?.(false, reason);
    return epoch;
  };

  async function send(request: Request, expected: number) {
    assertCurrent(expected);
    const controller = new AbortController();
    const abort = () => controller.abort();
    if (request.signal.aborted) abort();
    else request.signal.addEventListener('abort', abort, { once: true });
    controllers.add(controller);
    try {
      const response = await options.fetch(new Request(request, { signal: controller.signal }));
      assertCurrent(expected);
      return response;
    } finally {
      controllers.delete(controller);
      request.signal.removeEventListener('abort', abort);
    }
  }

  async function getCsrf(expected: number) {
    assertCurrent(expected);
    if (csrf) return csrf;
    if (csrfFlight?.epoch === expected) return csrfFlight.promise;
    const flight = {
      epoch: expected,
      promise: (async () => {
        const response = await send(new Request(new URL(`${apiBase}/api/auth/csrf`, options.origin),
          { credentials: 'include' }), expected);
        if (!response.ok) throw new AuthSessionError('인증 보호 정보를 받지 못했습니다.', response.status);
        const data = await response.json();
        assertCurrent(expected);
        if (typeof data.token !== 'string' || !data.token || data.headerName !== 'X-XSRF-TOKEN') {
          throw new AuthSessionError('인증 보호 응답이 올바르지 않습니다.');
        }
        csrf = { token: data.token, headerName: data.headerName };
        return csrf;
      })(),
    };
    csrfFlight = flight;
    try { return await flight.promise; }
    finally { if (csrfFlight === flight) csrfFlight = null; }
  }

  async function authPost(action: string, body: unknown, expected: number) {
    const protection = await getCsrf(expected);
    assertCurrent(expected);
    return send(new Request(new URL(`${apiBase}/api/auth/teacher/${action}`, options.origin), {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json', [protection!.headerName]: protection!.token },
      body: JSON.stringify(body),
    }), expected);
  }

  async function readToken(response: Response, expected: number): Promise<TokenResponse> {
    if (!response.ok) throw new AuthSessionError(
      response.status === 503 ? '인증 서비스를 사용할 수 없습니다. 다시 로그인해주세요.' : '로그인이 필요합니다.',
      response.status);
    const data = await response.json();
    assertCurrent(expected);
    if (typeof data.accessToken !== 'string' || !data.accessToken) {
      throw new AuthSessionError('로그인 응답이 올바르지 않습니다.');
    }
    return data;
  }

  async function refresh(expected: number) {
    assertCurrent(expected);
    if (refreshFlight?.epoch === expected) return refreshFlight.promise;
    const flight = {
      epoch: expected,
      promise: (async () => {
        try {
          const data = await readToken(await authPost('refresh', {}, expected), expected);
          assertCurrent(expected);
          options.storage.setItem('accessToken', data.accessToken);
          return data.accessToken;
        } catch (error) {
          if (epoch === expected) transition('expired');
          throw error;
        }
      })(),
    };
    refreshFlight = flight;
    try { return await flight.promise; }
    finally { if (refreshFlight === flight) refreshFlight = null; }
  }

  async function authenticatedFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const url = new URL(input instanceof Request ? input.url : String(input), options.origin);
    if (!inScope(url, apiScope) && !inScope(url, ragScope)) {
      throw new AuthSessionError('인증 API 요청 범위가 올바르지 않습니다.', 400);
    }
    if (url.origin === apiScope.origin && url.pathname.startsWith(`${apiScope.pathname}auth/`)) {
      throw new AuthSessionError('인증 요청은 전용 로그인 함수를 사용해야 합니다.', 400);
    }
    const expected = epoch;
    const requestToken = token();
    const template = new Request(input instanceof Request ? input : url, { ...init, credentials: 'include' });
    const attempt = (accessToken: string | null) => {
      assertCurrent(expected);
      const headers = new Headers(template.headers);
      headers.delete('Authorization');
      if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
      return send(new Request(template.clone(), { headers }), expected);
    };
    let response = await attempt(requestToken);
    if (response.status !== 401) return response; // A 403 is an authorization failure.
    if (!requestToken) {
      transition('expired');
      throw new AuthSessionError('로그인이 필요합니다.');
    }
    assertCurrent(expected);
    // A delayed 401 for the old AT must reuse an already refreshed AT.
    const current = token();
    const renewed = current && current !== requestToken ? current : await refresh(expected);
    assertCurrent(expected);
    response = await attempt(renewed); // At most one replay, including POST bodies.
    if (response.status === 401) {
      // Another request may already have refreshed this AT while our replay waited.
      // Keep that newer session; this individual request has exhausted its retry.
      if (token() === renewed) transition('expired');
      throw new AuthSessionError('로그인이 만료되었습니다. 다시 로그인해주세요.');
    }
    return response;
  }

  async function login(email: string, password: string) {
    const expected = transition();
    const data = await readToken(await authPost('login', { email, password }, expected), expected);
    assertCurrent(expected);
    options.storage.setItem('accessToken', data.accessToken);
    options.storage.setItem('isLoggedIn', 'true');
    if (data.teacherName) options.storage.setItem('teacherName', data.teacherName);
    options.onChange?.(true);
    return data;
  }

  async function logout() {
    // Invalidate immediately; even a late successful refresh cannot restore local state.
    // Server logout revokes the user's current Redis session using the presented RT.
    const expected = transition('logout');
    const response = await authPost('logout', {}, expected);
    if (!response.ok) throw new AuthSessionError(
      '이 기기에서 로그아웃했습니다. 서버 세션 폐기는 확인하지 못했습니다.', response.status);
  }

  return { authenticatedFetch, login, logout, clear: () => transition('expired'), getToken: token, getEpoch: () => epoch };
}
