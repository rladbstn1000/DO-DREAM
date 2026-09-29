import { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios';
import { getAccessToken, getRefreshToken, saveAccessToken, saveRefreshToken, clearTokens } from '../services/authStorage';
import { accessibilityUtil } from '../utils/accessibility';
import { createNativeTokenSession, safeRequestError } from './nativeTokenSession';

type AuthRequest = InternalAxiosRequestConfig & { _retry?: boolean; _authEpoch?: number; _authToken?: string | null };
const isAuthUrl = (url = '') => /\/api\/auth\/student\//.test(url);
export let nativeAuth: ReturnType<typeof createNativeTokenSession>;

export const setupInterceptors = (instance: AxiosInstance) => {
  nativeAuth = createNativeTokenSession({
    getAccessToken, getRefreshToken, clearTokens,
    saveTokens: ({ accessToken, refreshToken }) => { saveAccessToken(accessToken); saveRefreshToken(refreshToken); },
    post: async (path, body, signal) => (await instance.post(path, body, { signal, withCredentials: false })).data,
  });
  instance.interceptors.request.use((config: AuthRequest) => {
    if (isAuthUrl(config.url)) return config;
    config._authEpoch ??= nativeAuth.getEpoch();
    if (config._authEpoch !== nativeAuth.getEpoch()) throw new Error('Authentication state changed');
    config._authToken = getAccessToken();
    if (config._authToken) config.headers.set('Authorization', `Bearer ${config._authToken}`);
    else config.headers.delete('Authorization');
    return config;
  });
  instance.interceptors.response.use(
    response => {
      const config = response.config as AuthRequest;
      if (config._authEpoch !== undefined && config._authEpoch !== nativeAuth.getEpoch()) {
        throw new Error('Authentication state changed');
      }
      return response;
    },
    async (error: AxiosError) => {
      const original = error.config as AuthRequest | undefined;
      if (error.response?.status !== 401 || !original || original._retry || isAuthUrl(original.url)) throw safeRequestError(error);
      // Mark queued requests as retried too, so a rejected new AT cannot loop.
      original._retry = true;
      try {
        const token = await nativeAuth.refreshFor(original._authEpoch!, original._authToken ?? null);
        if (original._authEpoch !== nativeAuth.getEpoch()) throw new Error('Authentication state changed');
        original.headers.set('Authorization', `Bearer ${token}`);
        return instance(original);
      } catch (failure) {
        accessibilityUtil.announceWithVibration('로그인이 만료되었습니다. 다시 로그인해주세요.', 'warning');
        throw failure;
      }
    },
  );
};
