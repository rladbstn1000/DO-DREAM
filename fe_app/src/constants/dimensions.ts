/**
 * 앱 전체에서 사용하는 크기 관련 상수들
 */

/**
 * 헤더 버튼의 표준 높이
 * - BackButton, VoiceCommandButton, SettingsButton 등 헤더의 모든 버튼에 적용
 * - 모든 화면에서 일관된 버튼 높이를 유지하여 UI 통일성 확보
 */
export const HEADER_BTN_HEIGHT = 54;

/**
 * 헤더 컨테이너의 최소 높이
 * - HEADER_BTN_HEIGHT + 패딩(32px)으로 계산
 * - 헤더 내부 요소들이 수직으로 가운데 정렬될 수 있도록 충분한 공간 확보
 */
export const HEADER_MIN_HEIGHT = HEADER_BTN_HEIGHT + 32;
