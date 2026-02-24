import React, { useState, useEffect } from "react";
import {
  Modal,
  View,
  Text,
  Switch,
  TouchableOpacity,
  StyleSheet,
} from "react-native";
import type { Player, PlayerEventPrefs } from "@/types/api";
import { Colors } from "@/constants/colors";

interface PlayerEventModalProps {
  visible: boolean;
  onClose: () => void;
  player: Player | null;
  playerEventPrefs: PlayerEventPrefs;
  onToggle: (eventType: "home_run" | "strikeout", value: boolean) => void;
}

export function PlayerEventModal({
  visible,
  onClose,
  player,
  playerEventPrefs,
  onToggle,
}: PlayerEventModalProps) {
  // クローズアニメーション中もコンテンツを保持するためローカル状態で保持
  const [localPlayer, setLocalPlayer] = useState<Player | null>(null);

  useEffect(() => {
    if (player) setLocalPlayer(player);
  }, [player]);

  const displayPlayer = localPlayer;
  if (!displayPlayer) return null;

  const showHomeRun = displayPlayer.position === "batter" || displayPlayer.position === "two_way";
  const showStrikeout = displayPlayer.position === "pitcher" || displayPlayer.position === "two_way";

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      <TouchableOpacity style={styles.overlay} activeOpacity={1} onPress={onClose} />
      <View style={styles.sheet}>
        <View style={styles.handle} />
        <Text style={styles.title}>{displayPlayer.name_ja} の通知設定</Text>
        <Text style={styles.subtitle}>{displayPlayer.team} · {displayPlayer.name_en}</Text>

        <View style={styles.divider} />

        {showHomeRun && (
          <View style={styles.row}>
            <View style={styles.rowInfo}>
              <Text style={styles.rowEmoji}>⚾</Text>
              <Text style={styles.rowLabel}>ホームラン</Text>
            </View>
            <Switch
              value={playerEventPrefs.home_run ?? true}
              onValueChange={(v) => onToggle("home_run", v)}
              trackColor={{ false: Colors.disabled, true: Colors.accent }}
              thumbColor={Colors.text}
            />
          </View>
        )}

        {showStrikeout && (
          <View style={styles.row}>
            <View style={styles.rowInfo}>
              <Text style={styles.rowEmoji}>🔥</Text>
              <Text style={styles.rowLabel}>奪三振</Text>
            </View>
            <Switch
              value={playerEventPrefs.strikeout ?? true}
              onValueChange={(v) => onToggle("strikeout", v)}
              trackColor={{ false: Colors.disabled, true: Colors.accent }}
              thumbColor={Colors.text}
            />
          </View>
        )}

        <TouchableOpacity style={styles.closeBtn} onPress={onClose}>
          <Text style={styles.closeBtnText}>閉じる</Text>
        </TouchableOpacity>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.6)",
  },
  sheet: {
    backgroundColor: Colors.card,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: 24,
    paddingBottom: 40,
    borderTopWidth: 1,
    borderColor: Colors.border,
  },
  handle: {
    width: 40,
    height: 4,
    backgroundColor: Colors.border,
    borderRadius: 2,
    alignSelf: "center",
    marginBottom: 20,
  },
  title: {
    fontSize: 18,
    fontWeight: "700",
    color: Colors.text,
    marginBottom: 4,
  },
  subtitle: {
    fontSize: 13,
    color: Colors.subtext,
    marginBottom: 16,
  },
  divider: {
    height: 1,
    backgroundColor: Colors.border,
    marginBottom: 16,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 12,
  },
  rowInfo: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  rowEmoji: {
    fontSize: 22,
  },
  rowLabel: {
    fontSize: 16,
    color: Colors.text,
    fontWeight: "500",
  },
  closeBtn: {
    marginTop: 20,
    backgroundColor: Colors.background,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: "center",
    borderWidth: 1,
    borderColor: Colors.border,
  },
  closeBtnText: {
    color: Colors.subtext,
    fontSize: 15,
    fontWeight: "600",
  },
});
