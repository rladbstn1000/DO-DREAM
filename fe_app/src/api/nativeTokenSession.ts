type Tokens = { accessToken: string; refreshToken: string };
type Options = {
  getAccessToken: () => string | null;
  getRefreshToken: () => string | null;
  saveTokens: (tokens: Tokens) => void;
  clearTokens: () => void;
  post: (path: string, body: unknown, signal: AbortSignal) => Promise<Tokens | void>;
};

/** Axios errors contain request bodies/headers. Never propagate those to UI logs. */
export function safeRequestError(error: unknown): Error & { isAxiosError: true; code?: string; response?: { status: number; data: { message: string } } } {
  const value = error as { response?: { status?: unknown }; status?: unknown; code?: unknown } | null;
  const status = value?.response?.status ?? value?.status;
  const message = status === 503 ? '인증 서비스를 사용할 수 없습니다.'
    : status === 401 ? '다시 로그인해주세요.' : '요청을 완료하지 못했습니다.';
  const sanitized = new Error(message) as Error & { isAxiosError: true; code?: string; response?: { status: number; data: { message: string } } };
  sanitized.name = 'NativeRequestError';
  // Existing screens use axios.isAxiosError plus response.status for login guidance.
  sanitized.isAxiosError = true;
  if (value?.code === 'ECONNABORTED' || value?.code === 'ERR_CANCELED') sanitized.code = value.code;
  if (typeof status === 'number' && status >= 100 && status <= 599) {
    sanitized.response = { status, data: { message } };
  }
  return sanitized;
}

/** Explicit native token bodies; never depends on a browser cookie or platform header. */
export function createNativeTokenSession(options: Options) {
  let epoch = 0;
  let controller = new AbortController();
  let flight: { epoch: number; promise: Promise<string> } | null = null;
  async function post(path: string, body: unknown, signal: AbortSignal) {
    try { return await options.post(path, body, signal); }
    catch (error) { throw safeRequestError(error); }
  }
  const assertCurrent = (expected: number) => {
    if (epoch !== expected) throw new Error('Authentication state changed');
  };
  function advance() {
    epoch += 1;
    controller.abort();
    controller = new AbortController();
    flight = null;
    options.clearTokens();
    return epoch;
  }
  function accept(value: Tokens | void, expected: number): Tokens {
    assertCurrent(expected);
    if (!value || typeof value.accessToken !== 'string' || !value.accessToken ||
        typeof value.refreshToken !== 'string' || !value.refreshToken) {
      throw new Error('Invalid native token response');
    }
    options.saveTokens(value);
    return value;
  }
  async function login(credentials: { deviceId: string; deviceSecret: string }) {
    const expected = advance();
    return accept(await post('/api/auth/student/native/login', credentials, controller.signal), expected);
  }
  async function refreshFor(expected: number, usedAccessToken: string | null) {
    assertCurrent(expected);
    const current = options.getAccessToken();
    if (current && current !== usedAccessToken) return current;
    if (flight?.epoch === expected) return flight.promise;
    const operation = {
      epoch: expected,
      promise: (async () => {
        try {
          const refreshToken = options.getRefreshToken();
          if (!refreshToken) throw new Error('Login required after token contract update');
          return accept(await post('/api/auth/student/native/refresh', { refreshToken }, controller.signal), expected).accessToken;
        } catch (error) {
          if (epoch === expected) advance();
          throw error;
        }
      })(),
    };
    flight = operation;
    try { return await operation.promise; }
    finally { if (flight === operation) flight = null; }
  }
  async function refresh(): Promise<Tokens> {
    const expected = epoch;
    await refreshFor(expected, options.getAccessToken());
    assertCurrent(expected);
    return { accessToken: options.getAccessToken()!, refreshToken: options.getRefreshToken()! };
  }
  async function logout() {
    const refreshToken = options.getRefreshToken();
    const expected = advance();
    if (!refreshToken) throw new Error('Local logout completed; server revocation not confirmed');
    await post('/api/auth/student/native/logout', { refreshToken }, controller.signal);
    assertCurrent(expected);
  }
  return { login, refresh, refreshFor, logout, getEpoch: () => epoch, invalidate: advance };
}
