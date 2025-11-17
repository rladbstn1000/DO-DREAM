import React, {
  createContext,
  useCallback,
  useMemo,
  useRef,
  useState,
  useEffect,
} from "react";
import { AccessibilityInfo } from "react-native";
import { asrService } from "../services/asrService";

// 볼륨키 모드
type TriggerMode = "voice" | "playpause";

// 화면별로 등록할 음성 명령 핸들러들
type VoiceCommandHandlers = {
  playPause?: () => void;
  next?: () => void;
  prev?: () => void;
  openQuestion?: () => void;
  goBack?: () => void;
  openQuiz?: () => void;

  /**
   * 인식된 원문 텍스트를 그대로 받아 처리하는 핸들러
   *  - 예: LibraryScreen에서 "영어 1", "문학" → 교재 매칭
   */
  rawText?: (spoken: string) => void;
};

type Ctx = {
  mode: TriggerMode;
  setMode: (m: TriggerMode) => void;

  registerPlayPause: (fn: (() => void) | null) => void;
  getPlayPause: () => (() => void) | null;

  currentScreenId: string;
  setCurrentScreenId: (id: string) => void;

  registerVoiceHandlers: (
    screenId: string,
    handlers: VoiceCommandHandlers
  ) => void;

  startVoiceCommandListening: () => Promise<void>;
  stopVoiceCommandListening: () => Promise<void>;
  isVoiceCommandListening: boolean;
};

export const TriggerContext = createContext<Ctx>({
  mode: "voice",
  setMode: () => {},
  registerPlayPause: () => {},
  getPlayPause: () => null,
  currentScreenId: "",
  setCurrentScreenId: () => {},
  registerVoiceHandlers: () => {},
  startVoiceCommandListening: async () => {},
  stopVoiceCommandListening: async () => {},
  isVoiceCommandListening: false,
});

// 전역 공통 명령 키
type VoiceCommandKey =
  | "playPause"
  | "next"
  | "prev"
  | "openQuestion"
  | "goBack"
  | "openQuiz";

// 간단한 한국어 → 명령 키 매핑
function parseVoiceCommand(raw: string): VoiceCommandKey | null {
  const t = raw.trim().toLowerCase();
  if (!t) return null;

  // 뒤로가기 관련 명령어
  if (t.includes("뒤로") || t.includes("이전 화면") || t.includes("돌아가")) return "goBack";

  // 질문하기 관련 명령어 (단, "질문"만 단독으로 있을 때만 - 실제 질문 내용과 구분)
  if (t === "질문" || t === "질문하기" || t.includes("질문 하기") || t.includes("질문해줘")) return "openQuestion";

  // 퀴즈 관련 명령어
  if (t === "퀴즈" || t === "퀴즈 풀기" || t.includes("퀴즈 시작")) return "openQuiz";

  // 다음/이전 챕터- 이동 (명확한 네비게이션 명령만)
  if (t.includes("다음 챕터") || t.includes("다음장") || (t === "다음" && !t.includes("질문"))) return "next";
  if (t.includes("이전 챕터") || t.includes("앞장") || (t === "이전" && !t.includes("화면"))) return "prev";

  // 재생/일시정지 관련 명령어
  if (t.includes("재생") || t.includes("일시정지") || t.includes("멈춰") || t.includes("정지"))
    return "playPause";

  return null;
}

export function TriggerProvider({ children }: { children: React.ReactNode }) {
  // 재생/정지용 모드 & 핸들러
  const [mode, setMode] = useState<TriggerMode>("voice");
  const playPauseRef = useRef<(() => void) | null>(null);

  const registerPlayPause = useCallback((fn: (() => void) | null) => {
    playPauseRef.current = fn;
  }, []);

  const getPlayPause = useCallback(() => playPauseRef.current, []);

  // 전역 음성 명령 상태
  const [currentScreenId, setCurrentScreenId] = useState<string>("");
  const [isVoiceCommandListening, setIsVoiceCommandListening] =
    useState(false);

  const voiceHandlersRef = useRef<Record<string, VoiceCommandHandlers>>({});
  const asrOffRef = useRef<null | (() => void)>(null);

  // 일정 시간 동안 아무 것도 인식 안 될 때 자동 종료용 타이머
  const voiceTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const registerVoiceHandlers = useCallback(
    (screenId: string, handlers: VoiceCommandHandlers) => {
      voiceHandlersRef.current[screenId] = handlers;
    },
    []
  );

  const clearVoiceTimeout = useCallback(() => {
    if (voiceTimeoutRef.current) {
      clearTimeout(voiceTimeoutRef.current);
      voiceTimeoutRef.current = null;
    }
  }, []);

  const cleanupAsr = useCallback(() => {
    if (asrOffRef.current) {
      asrOffRef.current();
      asrOffRef.current = null;
    }
  }, []);

  const stopVoiceCommandListening = useCallback(async () => {
    clearVoiceTimeout();
    setIsVoiceCommandListening(false);
    cleanupAsr();
    try {
      await asrService.stop();
    } catch (e) {
      console.warn("[VoiceCommands] stopVoiceCommandListening 실패:", e);
    }
  }, [clearVoiceTimeout, cleanupAsr]);

  const startVoiceCommandListening = useCallback(async () => {
    // 이미 인식 중이면 무시 (토글은 버튼에서 처리)
    if (isVoiceCommandListening) return;

    // 이전 리스너/타이머 정리
    clearVoiceTimeout();
    cleanupAsr();

    // STT 결과 구독
    asrOffRef.current = asrService.on((raw, isFinal) => {
      if (!isFinal) return;

      const text = (raw || "").trim();
      if (!text) return;

      // 결과가 들어왔으므로 타임아웃 제거
      clearVoiceTimeout();

      // 한 번 결과 들어오면 바로 종료
      setIsVoiceCommandListening(false);
      asrService.stop().catch(() => {});
      cleanupAsr();

      const handlers =
        voiceHandlersRef.current[currentScreenId] ||
        ({} as VoiceCommandHandlers);

      // 전역 명령어 파싱 시도
      const key = parseVoiceCommand(text);

      // 1) 전역 명령어가 인식되었고, 해당 핸들러가 등록되어 있으면 실행
      if (key && handlers[key]) {
        console.log(
          "[VoiceCommands] 명령 실행:",
          key,
          "screen=",
          currentScreenId,
          "text=",
          text
        );
        try {
          handlers[key]!();
        } catch (e) {
          console.warn("[VoiceCommands] 핸들러 실행 중 오류:", e);
        }
        return;
      }

      // 2) 전역 명령어가 아니거나, 핸들러가 없으면 rawText 핸들러로 전달
      if (handlers.rawText) {
        console.log("[VoiceCommands] rawText 핸들러 호출:", text);
        try {
          handlers.rawText(text);
        } catch (e) {
          console.warn("[VoiceCommands] rawText 핸들러 실행 중 오류:", e);
        }
        return;
      }

      // 3) 아무 핸들러도 없으면 로그만 출력
      console.log(
        "[VoiceCommands] 처리할 수 없는 명령:",
        text,
        "screen=",
        currentScreenId,
        "parsedKey=",
        key
      );
    });

    setIsVoiceCommandListening(true);

    // 일정 시간 동안 아무 것도 안 들리면 자동 종료
    voiceTimeoutRef.current = setTimeout(() => {
      console.log(
        "[VoiceCommands] 타임아웃: 음성 명령 미인식으로 자동 종료"
      );
      setIsVoiceCommandListening(false);
      asrService.stop().catch(() => {});
      cleanupAsr();
      AccessibilityInfo.announceForAccessibility(
        "음성 명령을 인식하지 못해 듣기를 종료했습니다."
      );
    }, 6000); // 6초 정도 대기 (필요하면 숫자 조절 가능)

    try {
      await asrService.start({
        lang: "ko-KR",
        interimResults: false,
        continuous: false,
        autoRestart: false,
      });
    } catch (e) {
      console.warn("[VoiceCommands] asrService.start 실패:", e);
      clearVoiceTimeout();
      setIsVoiceCommandListening(false);
      cleanupAsr();
    }
  }, [
    cleanupAsr,
    clearVoiceTimeout,
    currentScreenId,
    isVoiceCommandListening,
  ]);

  // Provider 언마운트 시 ASR 정리
  useEffect(() => {
    return () => {
      clearVoiceTimeout();
      cleanupAsr();
      asrService.abort();
    };
  }, [cleanupAsr, clearVoiceTimeout]);

  const value = useMemo(
    () => ({
      mode,
      setMode,
      registerPlayPause,
      getPlayPause,
      currentScreenId,
      setCurrentScreenId,
      registerVoiceHandlers,
      startVoiceCommandListening,
      stopVoiceCommandListening,
      isVoiceCommandListening,
    }),
    [
      mode,
      registerPlayPause,
      getPlayPause,
      currentScreenId,
      registerVoiceHandlers,
      startVoiceCommandListening,
      stopVoiceCommandListening,
      isVoiceCommandListening,
    ]
  );

  return (
    <TriggerContext.Provider value={value}>{children}</TriggerContext.Provider>
  );
}
