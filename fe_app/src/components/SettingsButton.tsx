import React from "react";
import { TouchableOpacity, Text, StyleSheet, ViewStyle } from "react-native";
import { COLORS } from "../constants/colors";

interface SettingsButtonProps {
  onPress: () => void;
  style?: ViewStyle;
  showLabel?: boolean;
  accessibilityHint?: string;
}

export default function SettingsButton({
  onPress,
  style,
  showLabel = false,
  accessibilityHint = "재생 속도 및 화면 설정을 변경합니다.",
}: SettingsButtonProps) {
  return (
    <TouchableOpacity
      style={[styles.settingsButton, style]}
      onPress={onPress}
      accessible={true}
      accessibilityLabel={showLabel ? "사용자 설정" : "설정"}
      accessibilityRole="button"
      accessibilityHint={accessibilityHint}
      hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
    >
      <Text style={styles.settingsIcon}>
        {showLabel ? "⚙️ 설정" : "⚙️"}
      </Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  settingsButton: {
    minWidth: 56,
    minHeight: 52,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: COLORS.primary.lightest,
    borderColor: COLORS.primary.main,
    borderRadius: 12,
    borderWidth: 3,
    paddingVertical: 10,
    paddingHorizontal: 16,
    marginRight: 4,
  },
  settingsIcon: {
    fontSize: 18,
    color: COLORS.primary.main,
    fontWeight: "bold",
  },
});
