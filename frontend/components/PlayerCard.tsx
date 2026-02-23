import React from "react";
import {
  View,
  Text,
  Switch,
  StyleSheet,
  TouchableOpacity,
} from "react-native";
import type { Player, PlayerEventPrefs } from "@/types/api";
import { Colors } from "@/constants/colors";

const POSITION_LABEL: Record<Player["position"], string> = {
  batter: "打者",
  pitcher: "投手",
  two_way: "二刀流",
};

interface PlayerCardProps {
  player: Player;
  isSubscribed: boolean;
  eventPrefs?: PlayerEventPrefs;
  onToggle?: () => void;
  showToggle?: boolean;
  onSettingsPress?: () => void;
}

export function PlayerCard({
  player,
  isSubscribed,
  eventPrefs,
  onToggle,
  showToggle = true,
  onSettingsPress,
}: PlayerCardProps) {
  const canHomeRun = player.position === "batter" || player.position === "two_way";
  const canStrikeout = player.position === "pitcher" || player.position === "two_way";
  const isHomeRunEnabled = canHomeRun && (eventPrefs?.home_run ?? true);
  const isStrikeoutEnabled = canStrikeout && (eventPrefs?.strikeout ?? true);

  const enabledLabels = [
    isHomeRunEnabled && "HR",
    isStrikeoutEnabled && "奪三振",
  ].filter((v): v is string => typeof v === "string");
  return (
    <TouchableOpacity
      style={[styles.card, isSubscribed && styles.cardActive]}
      onPress={showToggle ? onToggle : undefined}
      activeOpacity={showToggle ? 0.7 : 1}
    >
      <View style={styles.info}>
        <View style={styles.nameRow}>
          <Text style={styles.nameJa}>{player.name_ja}</Text>
          {isSubscribed && <View style={styles.activeDot} />}
        </View>
        <Text style={styles.nameEn}>{player.name_en}</Text>
        <Text style={styles.meta}>
          {player.team} · {POSITION_LABEL[player.position]}
        </Text>
        {isSubscribed && (
          <View style={styles.eventRow}>
            {enabledLabels.length > 0 ? (
              enabledLabels.map((label) => (
                <View key={label} style={styles.eventChip}>
                  <Text style={styles.eventChipText}>{label}</Text>
                </View>
              ))
            ) : (
              <Text style={styles.noEventText}>通知なし</Text>
            )}
          </View>
        )}
      </View>
      {showToggle && (
        <Switch
          value={isSubscribed}
          onValueChange={onToggle}
          trackColor={{ false: Colors.disabled, true: Colors.accent }}
          thumbColor={Colors.text}
        />
      )}
      {!showToggle && onSettingsPress && (
        <TouchableOpacity onPress={onSettingsPress} style={styles.settingsBtn} hitSlop={8}>
          <Text style={styles.settingsIcon}>⚙️</Text>
        </TouchableOpacity>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: Colors.card,
    borderRadius: 12,
    padding: 16,
    marginVertical: 6,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  cardActive: {
    borderColor: Colors.accent,
  },
  info: {
    flex: 1,
    gap: 2,
  },
  nameRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  nameJa: {
    fontSize: 18,
    fontWeight: "700",
    color: Colors.text,
  },
  activeDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: Colors.success,
  },
  nameEn: {
    fontSize: 13,
    color: Colors.subtext,
  },
  meta: {
    fontSize: 12,
    color: Colors.subtext,
    marginTop: 2,
  },
  settingsBtn: {
    padding: 4,
  },
  settingsIcon: {
    fontSize: 20,
  },
  eventRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
    marginTop: 6,
  },
  eventChip: {
    backgroundColor: Colors.accent + "33",
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderWidth: 1,
    borderColor: Colors.accent,
  },
  eventChipText: {
    fontSize: 11,
    fontWeight: "600",
    color: Colors.accent,
  },
  noEventText: {
    fontSize: 11,
    color: Colors.subtext,
    fontStyle: "italic",
  },
});
