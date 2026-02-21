import React from "react";
import {
  View,
  Text,
  Switch,
  StyleSheet,
  TouchableOpacity,
} from "react-native";
import type { Player } from "@/types/api";
import { Colors } from "@/constants/colors";

const POSITION_LABEL: Record<Player["position"], string> = {
  batter: "打者",
  pitcher: "投手",
  two_way: "二刀流",
};

interface PlayerCardProps {
  player: Player;
  isSubscribed: boolean;
  onToggle?: () => void;
  showToggle?: boolean;
}

export function PlayerCard({
  player,
  isSubscribed,
  onToggle,
  showToggle = true,
}: PlayerCardProps) {
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
      </View>
      {showToggle && (
        <Switch
          value={isSubscribed}
          onValueChange={onToggle}
          trackColor={{ false: Colors.disabled, true: Colors.accent }}
          thumbColor={Colors.text}
        />
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
});
