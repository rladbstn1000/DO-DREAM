import apiClient from "./apiClient";
import { nativeAuth } from './interceptors';
import type {
  StudentVerifyRequest,
  StudentRegisterRequest,
  StudentLoginRequest,
  AuthResponse,
  VerifyResponse,
} from "../types/api/authApiTypes";

const AUTH_ENDPOINTS = {
  VERIFY: "/api/auth/student/verify", // 사전 인증 (학번/이름 확인)
  REGISTER: "/api/auth/student/register", // 회원가입 (기기 등록)
};

export const authApi = {
  invalidateLocalSession: () => nativeAuth.invalidate(),
  /**
   * 학생 사전 인증 (1단계)
   * 학번과 이름이 더미레지스트리에 있는지 확인
   */
  verify: async (data: StudentVerifyRequest): Promise<VerifyResponse> => {
    const response = await apiClient.post(AUTH_ENDPOINTS.VERIFY, data);
    return response.data;
  },

  /**
   * 학생 회원가입 (2단계)
   * 사전 인증 후 기기 정보와 생체인증 시크릿 등록
   */
  register: async (data: StudentRegisterRequest): Promise<AuthResponse> => {
    const response = await apiClient.post(AUTH_ENDPOINTS.REGISTER, data);
    return response.data;
  },

  /**
   * 학생 로그인
   * Native 기기 시크릿 로그인. 명시적 AT/RT 응답을 기존 앱 저장소에 저장.
   */
  login: async (data: StudentLoginRequest): Promise<AuthResponse> => {
    return nativeAuth.login(data);
  },

  /**
   * 학생 토큰 재발급
   * Native RT를 본문으로 전달해 회전. 브라우저 쿠키를 사용하지 않음.
   */
  refresh: async (): Promise<AuthResponse> => {
    return nativeAuth.refresh();
  },

  /**
   * Native RT로 서버 세션 폐기. 실패 시 성공으로 처리하지 않음.
   */
  logout: async (): Promise<void> => {
    await nativeAuth.logout();
  },
};
