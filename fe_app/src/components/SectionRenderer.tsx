import React from "react";
import { View, Text, StyleSheet } from "react-native";
import type { Section } from "../types/chapter";
import { COLORS } from "../constants/colors";

export default function SectionRenderer({ section }: {   section: Section  }) {
  if (!section) return null;

  const { type, text } = section;

  /** -----------------------------
   * list 타입 (A안)
   * ----------------------------- */
  if (type === "list") {
    const [title, ...bodyParts] = text.split("\n");
    const body = bodyParts.join("\n").trim();

    return (
      <View
        style={styles.listContainer}
        accessible={true}
        accessibilityRole="summary"   // ★ 수정됨: listitem → summary
      >
        <Text style={styles.listTitle}>{title}</Text>
        {body.length > 0 && <Text style={styles.listBody}>{body}</Text>}
      </View>
    );
  }

  /** -----------------------------
   * heading
   * ----------------------------- */
  if (type === "heading") {
    return (
      <View
        style={styles.headingContainer}
        accessible={true}
        accessibilityRole="header"
      >
        <Text style={styles.headingText}>{text}</Text>
      </View>
    );
  }

  /** -----------------------------
   * paragraph
   * ----------------------------- */
  return (
    <View
      style={styles.paragraphContainer}
      accessible={true}
      accessibilityRole="text"
    >
      <Text style={[styles.paragraphText]}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  headingContainer: {
    marginBottom: 20,
  },
  headingText: {
    fontSize: 32,
    fontWeight: "800",
    color: COLORS.text.primary,
    lineHeight: 44,
  },

  listContainer: {
    marginBottom: 24,
    padding: 16,
    borderRadius: 12,
    borderWidth: 2,
    borderColor: COLORS.secondary.main,
    backgroundColor: COLORS.secondary.lightest,
  },
  listTitle: {
    fontSize: 28,
    fontWeight: "800",
    color: COLORS.text.primary,
    marginBottom: 6,
  },
  listBody: {
    fontSize: 24,
    lineHeight: 38,
    fontWeight: "500",
    color: COLORS.text.secondary,
  },

  paragraphContainer: {
    marginBottom: 24,
  },
  paragraphText: {
    fontSize: 28,
    lineHeight: 44,
    fontWeight: "500",
    color: COLORS.text.primary,
  },
});
