import React, {
  useState,
  useEffect,
  useRef,
  useContext,
  useCallback,
  useMemo,
} from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  AccessibilityInfo,
  Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useNavigation, useRoute } from "@react-navigation/native";
import {
  BookmarkListScreenNavigationProp,
  BookmarkListScreenRouteProp,
} from "../../navigation/navigationTypes";
import ttsService from "../../services/ttsService";
import * as Haptics from "expo-haptics";
import { TriggerContext } from "../../triggers/TriggerContext";
import BackButton from "../../components/BackButton";
import VoiceCommandButton from "../../components/VoiceCommandButton";
import { commonStyles } from "../../styles/commonStyles";
import { buildChaptersFromMaterialJson } from "../../utils/materialJsonMapper";
import type { Chapter } from "../../types/chapter";
import { fetchAllBookmarks, toggleBookmark } from "../../api/bookmarkApi";
import type { BookmarkListItem } from "../../types/api/bookmarkApiTypes";
import { COLORS } from "../../constants/colors";

export default function BookmarkListScreen() {
  const navigation = useNavigation<BookmarkListScreenNavigationProp>();
  const route = useRoute<BookmarkListScreenRouteProp>();
  const { material, chapterId } = route.params;

  // 이 화면에서 사용할 뷰 모델 타입
  type BookmarkViewItem = BookmarkListItem & {
    sectionType: "paragraph" | "heading" | "formula" | "image_description";
  };

  const [bookmarks, setBookmarks] = useState<BookmarkViewItem[]>([]);
  const [isReviewMode, setIsReviewMode] = useState(false);
  const [currentReviewIndex, setCurrentReviewIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const scrollViewRef = useRef<ScrollView>(null);

  // JSON → Chapter[] 변환 (챕터 제목 표시용)
  const chaptersFromJson: Chapter[] = useMemo(() => {
    const anyMaterial: any = material;
    const json = anyMaterial?.json;
    if (json && Array.isArray(json.chapters)) {
      return buildChaptersFromMaterialJson(material.id, json);
    }
    return [];
  }, [material]);

  const chapter: Chapter | null =
    chapterId !== undefined
      ? chaptersFromJson.find((c) => c.chapterId === chapterId) ?? null
      : null;

  // 전역 음성 명령 컨텍스트
  const { setCurrentScreenId, registerVoiceHandlers } =
    useContext(TriggerContext);

  // 서버에서 저장 목록 로드 (이 교재 + 이 챕터)
  const loadBookmarks = useCallback(async () => {
    try {
      const all = await fetchAllBookmarks();

      const chapterIdStr = String(chapterId);
      const filtered: BookmarkViewItem[] = all
        .filter(
          (b) => b.materialId === material.id && b.titleId === chapterIdStr
        )
        .map((b) => ({
          ...b,
          sectionType: "paragraph", // 타이틀 단위 저장이라 일단 본문으로 통일
        }));

      setBookmarks(filtered);
    } catch (error) {
      console.error("[BookmarkListScreen] 저장 목록 로드 실패:", error);
      AccessibilityInfo.announceForAccessibility(
        "저장된 내용을 불러오지 못했습니다."
      );
    }
  }, [material.id, chapterId]);

  useEffect(() => {
    loadBookmarks();
  }, [loadBookmarks]);

  // 화면 진입 시 안내 (간단 버전)
  useEffect(() => {
    const count = bookmarks.length;
    const announcement =
      count > 0
        ? `저장된 내용 화면입니다. 지금 저장된 내용이 ${count}개 있습니다. 항목을 탭하면 그 위치로 이동하고, 길게 누르면 내용을 들을 수 있습니다.`
        : "저장된 내용 화면입니다. 아직 저장한 내용이 없습니다. 학습 중 중요한 부분에서 저장 버튼을 누르면 이곳에 모입니다.";

    const timer = setTimeout(() => {
      AccessibilityInfo.announceForAccessibility(announcement);
    }, 500);

    return () => clearTimeout(timer);
  }, [bookmarks.length]);

  // 복습 모드 종료 시 정리
  useEffect(() => {
    return () => {
      if (isReviewMode) {
        ttsService.stop();
      }
    };
  }, [isReviewMode]);

  const handleGoBack = useCallback(() => {
    if (isReviewMode) {
      ttsService.stop();
    }
    AccessibilityInfo.announceForAccessibility("이전 화면으로 이동합니다.");
    navigation.goBack();
  }, [navigation, isReviewMode]);

  // 단일 저장된 내용 재생 (서버 contents 사용)
  const handlePlayBookmark = async (bookmark: BookmarkViewItem) => {
    try {
      await ttsService.initialize(
        [
          {
            id: 0,
            text: bookmark.contents,
            type: "paragraph",
          },
        ],
        0,
        {
          rate: 1.0,
          playMode: "single",
          onStart: () => {
            setIsPlaying(true);
          },
          onDone: () => {
            setIsPlaying(false);
            AccessibilityInfo.announceForAccessibility("재생이 끝났습니다.");
          },
          onError: (error) => {
            console.error("TTS Error:", error);
            setIsPlaying(false);
            AccessibilityInfo.announceForAccessibility(
              "음성 재생 중 오류가 발생했습니다."
            );
          },
        }
      );

      await ttsService.play();
      AccessibilityInfo.announceForAccessibility(
        `저장된 내용을 재생합니다. 제목: ${bookmark.title}`
      );
      Haptics.selectionAsync();
    } catch (error) {
      console.error("[Bookmark] Play error:", error);
      AccessibilityInfo.announceForAccessibility(
        "저장된 내용을 재생할 수 없습니다."
      );
    }
  };

  // 복습 모드 시작 (서버 contents를 순서대로 재생)
  const handleStartReviewMode = useCallback(async () => {
    if (bookmarks.length === 0) {
      AccessibilityInfo.announceForAccessibility("저장된 내용이 없습니다.");
      return;
    }

    setIsReviewMode(true);
    setCurrentReviewIndex(0);

    try {
      const sections = bookmarks.map((b, idx) => ({
        id: idx,
        text: b.contents,
        type: "paragraph" as const,
      }));

      await ttsService.initialize(sections, 0, {
        rate: 1.0,
        playMode: "repeat",
        repeatCount: 2,
        pauseSettings: {
          heading: 3000,
          paragraph: 3000,
          formula: 3000,
          imageDescription: 3000,
          default: 3000,
        },
        onStart: () => {
          setIsPlaying(true);
        },
        onSectionChange: (index) => {
          setCurrentReviewIndex(index);
          AccessibilityInfo.announceForAccessibility(
            `${index + 1}번째 내용입니다. 총 ${bookmarks.length}개 중입니다.`
          );
        },
        onDone: () => {
          setIsPlaying(false);
          setIsReviewMode(false);
          setCurrentReviewIndex(0);
          AccessibilityInfo.announceForAccessibility(
            "저장된 내용을 모두 들었습니다."
          );
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        },
        onError: (error) => {
          console.error("TTS Error:", error);
          setIsPlaying(false);
          setIsReviewMode(false);
          AccessibilityInfo.announceForAccessibility(
            "음성 재생 중 오류가 발생했습니다."
          );
        },
      });

      await ttsService.play();
      AccessibilityInfo.announceForAccessibility(
        "복습 모드를 시작합니다. 저장된 내용을 순서대로 두 번씩 재생합니다."
      );
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch (error) {
      console.error("[ReviewMode] Start error:", error);
      setIsReviewMode(false);
      AccessibilityInfo.announceForAccessibility(
        "복습 모드를 시작할 수 없습니다."
      );
    }
  }, [bookmarks]);

  // 복습 모드 중지
  const handleStopReviewMode = useCallback(async () => {
    await ttsService.stop();
    setIsPlaying(false);
    setIsReviewMode(false);
    setCurrentReviewIndex(0);
    AccessibilityInfo.announceForAccessibility("복습 모드를 중지했습니다.");
    Haptics.selectionAsync();
  }, []);

  // 저장 삭제 (서버 토글 사용)
  const handleDeleteBookmark = (bookmark: BookmarkViewItem) => {
    Alert.alert(
      "저장 삭제",
      `${bookmark.title} 항목을 삭제하시겠습니까?`,
      [
        {
          text: "취소",
          style: "cancel",
          onPress: () =>
            AccessibilityInfo.announceForAccessibility("취소했습니다."),
        },
        {
          text: "삭제",
          style: "destructive",
          onPress: async () => {
            try {
              await toggleBookmark({
                materialId: bookmark.materialId,
                titleId: bookmark.titleId,
              });

              setBookmarks((prev) =>
                prev.filter((b) => b.bookmarkId !== bookmark.bookmarkId)
              );

              AccessibilityInfo.announceForAccessibility(
                "저장된 내용을 삭제했습니다."
              );
              Haptics.notificationAsync(
                Haptics.NotificationFeedbackType.Success
              );
            } catch (error) {
              console.error("[Bookmark] 삭제 실패:", error);
              AccessibilityInfo.announceForAccessibility(
                "삭제에 실패했습니다."
              );
            }
          },
        },
      ]
    );
  };

  // 저장된 항목을 눌러 해당 챕터로 이동 (챕터 맨 앞 섹션으로 이동)
  const handleGoToSection = (bookmark: BookmarkViewItem) => {
    if (isReviewMode) {
      AccessibilityInfo.announceForAccessibility(
        "복습 모드를 먼저 중지해 주세요."
      );
      return;
    }

    navigation.navigate("Player", {
      material,
      chapterId,
      fromStart: false,
      initialSectionIndex: 0,
    });
  };

  const formatDate = (isoString: string) => {
    const date = new Date(isoString);
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    return `${month}/${day} ${hours}:${minutes}`;
  };

  const getSectionTypeLabel = (type: string) => {
    switch (type) {
      case "heading":
        return "제목";
      case "paragraph":
        return "본문";
      case "formula":
        return "수식";
      case "image_description":
        return "이미지 설명";
      default:
        return "내용";
    }
  };

  // 음성 명령 등록
  useEffect(() => {
    setCurrentScreenId("BookmarkList");

    registerVoiceHandlers("BookmarkList", {
      playPause: () => {
        if (isReviewMode) {
          handleStopReviewMode();
        } else {
          handleStartReviewMode();
        }
      },
      goBack: handleGoBack,
    });

    return () => {
      registerVoiceHandlers("BookmarkList", {});
    };
  }, [
    setCurrentScreenId,
    registerVoiceHandlers,
    handleGoBack,
    handleStartReviewMode,
    handleStopReviewMode,
    isReviewMode,
  ]);

  return (
    <SafeAreaView style={styles.container}>
      {/* 헤더: 뒤로 / 제목 / 음성 명령 */}
      <View style={[commonStyles.headerContainer, styles.header]}>
        <BackButton
          onPress={handleGoBack}
          style={commonStyles.headerBackButton}
        />

        <View style={styles.headerTitle}>
          <Text
            style={styles.titleText}
            accessible={true}
            accessibilityRole="header"
          >
            저장된 내용
          </Text>
          <Text style={styles.countText}>{bookmarks.length}개</Text>
        </View>

        <View style={styles.headerRight}>
          <VoiceCommandButton
            style={[commonStyles.headerVoiceButton]}
            accessibilityHint="두 번 탭한 뒤 복습 시작, 복습 중지, 뒤로 가기라고 말해 보세요."
          />
        </View>
      </View>

      {/* 챕터 정보 */}
      <View style={styles.chapterInfo}>
        <Text style={styles.subjectText}>{material.title}</Text>
        <Text style={styles.chapterTitle}>
          {chapter ? chapter.title : `${chapterId}챕터`}
        </Text>
      </View>

      {/* 저장 목록 */}
      <ScrollView
        ref={scrollViewRef}
        style={styles.listArea}
        contentContainerStyle={styles.listContent}
        showsVerticalScrollIndicator={false}
        accessible={false}
      >
        {bookmarks.length === 0 ? (
          <View style={styles.emptyContainer}>
            <Text
              style={styles.emptyText}
              accessible={true}
              accessibilityRole="text"
            >
              저장한 내용이 없습니다
            </Text>
            <Text
              style={styles.emptyHint}
              accessible={true}
              accessibilityRole="text"
            >
              학습 중 중요한 부분에서{"\n"}저장 버튼을 눌러 보세요
            </Text>
          </View>
        ) : (
          bookmarks.map((bookmark, index) => (
            <View
              key={bookmark.bookmarkId}
              style={[
                styles.bookmarkCard,
                isReviewMode &&
                  currentReviewIndex === index &&
                  styles.activeBookmarkCard,
              ]}
            >
              {/* 저장된 내용 (탭: 챕터로 이동, 길게: 재생) */}
              <TouchableOpacity
                style={styles.bookmarkContent}
                onPress={() => handleGoToSection(bookmark)}
                onLongPress={() => handlePlayBookmark(bookmark)}
                accessible={true}
                accessibilityLabel={`${index + 1}번째 저장된 내용. ${getSectionTypeLabel(
                  bookmark.sectionType
                )}. 제목 ${bookmark.title}. 저장 시간 ${formatDate(
                  bookmark.createdAt
                )}.`}
                accessibilityRole="button"
                accessibilityHint="탭하면 그 위치로 이동하고, 길게 누르면 내용을 들을 수 있습니다."
              >
                <View style={styles.bookmarkHeader}>
                  <Text style={styles.sectionNumber}>#{index + 1}</Text>
                  <Text style={styles.sectionType}>
                    {getSectionTypeLabel(bookmark.sectionType)}
                  </Text>
                </View>

                <Text style={styles.bookmarkTitle}>{bookmark.title}</Text>
                <Text style={styles.bookmarkText}>{bookmark.contents}</Text>

                <View style={styles.bookmarkFooter}>
                  <Text style={styles.dateText}>
                    {formatDate(bookmark.createdAt)}
                  </Text>
                </View>
              </TouchableOpacity>

              {/* 삭제 버튼 */}
              <TouchableOpacity
                style={styles.deleteButton}
                onPress={() => handleDeleteBookmark(bookmark)}
                accessible={true}
                accessibilityLabel="저장된 내용 삭제"
                accessibilityRole="button"
                accessibilityHint="이 저장된 내용을 삭제합니다."
                hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
              >
                <Text style={styles.deleteButtonText}>🗑️</Text>
              </TouchableOpacity>
            </View>
          ))
        )}
      </ScrollView>

      {/* 하단 복습 모드 버튼 */}
      {bookmarks.length > 0 && (
        <View style={styles.bottomContainer}>
          {isReviewMode ? (
            <View style={styles.reviewModeActive}>
              <View style={styles.reviewInfo}>
                <Text style={styles.reviewInfoText}>
                  {`🔄 복습 중: ${currentReviewIndex + 1} / ${
                    bookmarks.length
                  }`}
                </Text>
                <Text style={styles.reviewSubText}>
                  각 저장된 내용을 2회씩 반복합니다
                </Text>
              </View>
              <TouchableOpacity
                style={styles.stopButton}
                onPress={handleStopReviewMode}
                accessible={true}
                accessibilityLabel="복습 모드 중지"
                accessibilityRole="button"
                accessibilityHint="복습을 멈춥니다."
              >
                <Text style={styles.stopButtonText}>⏹ 중지</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <TouchableOpacity
              style={styles.reviewButton}
              onPress={handleStartReviewMode}
              accessible={true}
              accessibilityLabel="복습 모드 시작"
              accessibilityRole="button"
              accessibilityHint="저장된 내용을 순서대로 두 번씩 들을 수 있습니다."
            >
              <Text style={styles.reviewButtonText}>🔄 복습 모드</Text>
              <Text style={styles.reviewButtonSubtext}>
                저장된 내용을 각 2회씩 반복 재생
              </Text>
            </TouchableOpacity>
          )}
        </View>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background.default,
  },
  header: {
    borderBottomWidth: 3,
    borderBottomColor: COLORS.border.light,
  },
  headerTitle: {
    alignItems: "center",
  },
  titleText: {
    fontSize: 28,
    fontWeight: "bold",
    color: COLORS.text.primary,
  },
  countText: {
    fontSize: 22,
    color: COLORS.text.secondary,
    marginTop: 4,
  },
  // 헤더 오른쪽: 음성 명령 버튼 영역
  headerRight: {
    flexDirection: "row",
    alignItems: "center",
  },
  chapterInfo: {
    paddingHorizontal: 20,
    paddingVertical: 16,
    backgroundColor: COLORS.background.elevated,
    borderBottomWidth: 2,
    borderBottomColor: COLORS.border.light,
  },
  subjectText: {
    fontSize: 22,
    color: COLORS.text.secondary,
    marginBottom: 4,
  },
  chapterTitle: {
    fontSize: 26,
    fontWeight: "bold",
    color: COLORS.text.primary,
  },
  listArea: {
    flex: 1,
  },
  listContent: {
    padding: 16,
  },
  emptyContainer: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    paddingVertical: 80,
  },
  emptyText: {
    fontSize: 28,
    fontWeight: "bold",
    color: COLORS.text.tertiary,
    marginBottom: 12,
  },
  emptyHint: {
    fontSize: 24,
    color: COLORS.border.main,
    textAlign: "center",
    lineHeight: 34,
  },
  errorText: {
    fontSize: 26,
    color: COLORS.text.secondary,
    fontWeight: "600",
  },
  bookmarkCard: {
    backgroundColor: COLORS.background.default,
    borderRadius: 16,
    marginBottom: 20,
    borderWidth: 3,
    borderColor: COLORS.secondary.main,
    overflow: "hidden",
    flexDirection: "row",
    minHeight: 140,
  },
  activeBookmarkCard: {
    borderColor: COLORS.status.success,
    backgroundColor: COLORS.status.successLight,
  },
  bookmarkContent: {
    flex: 1,
    padding: 20,
  },
  bookmarkHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 12,
  },
  sectionNumber: {
    fontSize: 24,
    fontWeight: "bold",
    color: COLORS.secondary.dark,
  },
  sectionType: {
    fontSize: 18,
    color: COLORS.text.secondary,
    backgroundColor: COLORS.secondary.lightest,
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 8,
    fontWeight: "600",
  },
  bookmarkTitle: {
    fontSize: 24,
    fontWeight: "700",
    color: COLORS.text.primary,
    marginBottom: 6,
  },
  bookmarkText: {
    fontSize: 20,
    lineHeight: 34,
    color: COLORS.text.secondary,
    marginBottom: 12,
    fontWeight: "500",
  },
  bookmarkFooter: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  dateText: {
    fontSize: 16,
    color: COLORS.text.tertiary,
  },
  deleteButton: {
    width: 80,
    backgroundColor: COLORS.status.error,
    justifyContent: "center",
    alignItems: "center",
    minHeight: 140,
  },
  deleteButtonText: {
    fontSize: 36,
  },
  bottomContainer: {
    paddingHorizontal: 20,
    paddingVertical: 20,
    borderTopWidth: 3,
    borderTopColor: COLORS.border.light,
    backgroundColor: COLORS.background.elevated,
  },
  reviewButton: {
    backgroundColor: COLORS.status.success,
    borderRadius: 16,
    padding: 24,
    alignItems: "center",
    minHeight: 100,
    justifyContent: "center",
    borderWidth: 3,
    borderColor: COLORS.status.success,
  },
  reviewButtonText: {
    fontSize: 30,
    fontWeight: "bold",
    color: COLORS.text.inverse,
    marginBottom: 8,
  },
  reviewButtonSubtext: {
    fontSize: 22,
    color: COLORS.status.successLight,
    fontWeight: "700",
  },
  reviewModeActive: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  reviewInfo: {
    flex: 1,
  },
  reviewInfoText: {
    fontSize: 26,
    fontWeight: "bold",
    color: COLORS.status.success,
    marginBottom: 6,
  },
  reviewSubText: {
    fontSize: 22,
    color: COLORS.text.secondary,
    fontWeight: "600",
  },
  stopButton: {
    backgroundColor: COLORS.status.error,
    borderRadius: 12,
    paddingVertical: 20,
    paddingHorizontal: 28,
    minHeight: 72,
    justifyContent: "center",
    alignItems: "center",
    borderWidth: 3,
    borderColor: COLORS.status.error,
  },
  stopButtonText: {
    fontSize: 26,
    fontWeight: "bold",
    color: COLORS.text.inverse,
  },
});
