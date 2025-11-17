import { StyleSheet } from "react-native";
import { COLORS } from "../constants/colors";

export const commonStyles = StyleSheet.create({
  // 컨테이너
  container: {
    flex: 1,
    backgroundColor: COLORS.background.default,
  },

  // 화면 상단 헤더 컨테이너
  headerContainer: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 24,
    paddingVertical: 16,
    backgroundColor: COLORS.background.default,
    borderBottomWidth: 3, // 두꺼운 경계선 (접근성)
    borderBottomColor: COLORS.primary.main,
  },
  headerBackButton: {
    padding: 0,
    minWidth: 88, // 충분한 터치 영역
    minHeight: 44,
  },
  headerVoiceButton: {
    padding: 0,
    minWidth: 88,
    minHeight: 44,
  },

  // 메인 버튼 (Primary)
  primaryButton: {
    backgroundColor: COLORS.primary.main,
    borderWidth: 4,
    borderColor: COLORS.primary.dark,
    padding: 28,
    borderRadius: 16,
    minHeight: 130,
    alignItems: "center",
    justifyContent: "center",
  },
  primaryButtonText: {
    color: COLORS.text.inverse,
    fontSize: 26,
    fontWeight: "bold",
  },

  // 보조 버튼 (Secondary)
  secondaryButton: {
    backgroundColor: COLORS.secondary.main,
    borderWidth: 4,
    borderColor: COLORS.secondary.dark,
    padding: 28,
    borderRadius: 16,
    minHeight: 130,
    alignItems: "center",
    justifyContent: "center",
  },
  secondaryButtonText: {
    color: COLORS.text.primary, // 노란 배경에는 검은 텍스트
    fontSize: 26,
    fontWeight: "bold",
  },

  // 텍스트 스타일
  title: {
    fontSize: 52,
    fontWeight: "bold",
    color: COLORS.primary.main,
    marginBottom: 16,
  },
  subtitle: {
    fontSize: 32,
    fontWeight: "600",
    color: COLORS.text.secondary,
    marginBottom: 12,
  },
  bodyText: {
    fontSize: 20,
    color: COLORS.text.primary,
    lineHeight: 30,
  },
  smallText: {
    fontSize: 18,
    color: COLORS.text.tertiary,
  },

  // 입력 필드
  input: {
    fontSize: 26,
    padding: 18,
    borderWidth: 3,
    borderColor: COLORS.border.main,
    borderRadius: 12,
    backgroundColor: COLORS.background.default,
    color: COLORS.text.primary,
    minHeight: 60,
  },
  inputFocused: {
    borderColor: COLORS.primary.main,
    borderWidth: 4,
  },

  // 카드/박스
  card: {
    backgroundColor: COLORS.primary.lightest,
    borderWidth: 2,
    borderColor: COLORS.primary.main,
    borderRadius: 12,
    padding: 24,
    marginBottom: 16,
  },

  // 여백
  marginBottom16: {
    marginBottom: 16,
  },
  marginBottom24: {
    marginBottom: 24,
  },
  marginBottom32: {
    marginBottom: 32,
  },

  // 중앙 정렬
  centerContent: {
    alignItems: "center",
    justifyContent: "center",
  },
});