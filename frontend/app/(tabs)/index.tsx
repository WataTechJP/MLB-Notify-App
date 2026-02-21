import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
} from "react-native";
import { usePushToken } from "@/hooks/usePushToken";
import { usePreferences } from "@/hooks/usePreferences";
import { PlayerCard } from "@/components/PlayerCard";
import { Colors } from "@/constants/colors";

export default function HomeScreen() {
  const { token } = usePushToken();
  const { players, preferences, isLoading, error, refresh } =
    usePreferences(token);

  const subscribedPlayers = players.filter((p) =>
    preferences?.player_ids.includes(p.id)
  );

  if (isLoading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.accent} />
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={isLoading}
          onRefresh={refresh}
          tintColor={Colors.accent}
        />
      }
    >
      <Text style={styles.heading}>MLB 日本人選手</Text>
      <Text style={styles.subheading}>⚾ 通知ダッシュボード</Text>

      {error && (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      )}

      {/* 通知イベント設定サマリー */}
      {preferences && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>通知設定</Text>
          <View style={styles.summaryRow}>
            <SummaryBadge
              label="ホームラン"
              active={preferences.event_prefs.home_run}
              emoji="💥"
            />
            <SummaryBadge
              label="奪三振"
              active={preferences.event_prefs.strikeout}
              emoji="🔥"
            />
          </View>
        </View>
      )}

      {/* フォロー中の選手 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>
          フォロー中の選手 ({subscribedPlayers.length})
        </Text>
        {subscribedPlayers.length === 0 ? (
          <View style={styles.emptyBox}>
            <Text style={styles.emptyText}>
              設定タブから選手を選んでください
            </Text>
          </View>
        ) : (
          subscribedPlayers.map((player) => (
            <PlayerCard
              key={player.id}
              player={player}
              isSubscribed={true}
              showToggle={false}
            />
          ))
        )}
      </View>
    </ScrollView>
  );
}

function SummaryBadge({
  label,
  active,
  emoji,
}: {
  label: string;
  active: boolean;
  emoji: string;
}) {
  return (
    <View style={[styles.badge, active ? styles.badgeActive : styles.badgeInactive]}>
      <Text style={styles.badgeEmoji}>{emoji}</Text>
      <Text style={[styles.badgeLabel, !active && styles.badgeLabelInactive]}>
        {label}
      </Text>
      <Text style={[styles.badgeStatus, active ? styles.statusOn : styles.statusOff]}>
        {active ? "ON" : "OFF"}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  content: {
    padding: 20,
    paddingTop: 16,
  },
  centered: {
    flex: 1,
    backgroundColor: Colors.background,
    alignItems: "center",
    justifyContent: "center",
  },
  heading: {
    fontSize: 26,
    fontWeight: "800",
    color: Colors.text,
    marginBottom: 4,
  },
  subheading: {
    fontSize: 14,
    color: Colors.subtext,
    marginBottom: 24,
  },
  section: {
    marginBottom: 28,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: "600",
    color: Colors.subtext,
    textTransform: "uppercase",
    letterSpacing: 1,
    marginBottom: 12,
  },
  summaryRow: {
    flexDirection: "row",
    gap: 12,
  },
  badge: {
    flex: 1,
    borderRadius: 12,
    padding: 16,
    alignItems: "center",
    gap: 4,
    borderWidth: 1,
  },
  badgeActive: {
    backgroundColor: Colors.card,
    borderColor: Colors.accent,
  },
  badgeInactive: {
    backgroundColor: Colors.card,
    borderColor: Colors.border,
  },
  badgeEmoji: {
    fontSize: 24,
  },
  badgeLabel: {
    fontSize: 13,
    fontWeight: "600",
    color: Colors.text,
  },
  badgeLabelInactive: {
    color: Colors.subtext,
  },
  badgeStatus: {
    fontSize: 11,
    fontWeight: "700",
  },
  statusOn: {
    color: Colors.success,
  },
  statusOff: {
    color: Colors.subtext,
  },
  emptyBox: {
    backgroundColor: Colors.card,
    borderRadius: 12,
    padding: 24,
    alignItems: "center",
    borderWidth: 1,
    borderColor: Colors.border,
    borderStyle: "dashed",
  },
  emptyText: {
    color: Colors.subtext,
    fontSize: 14,
  },
  errorBox: {
    backgroundColor: "#2a1a1a",
    borderRadius: 12,
    padding: 14,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: Colors.accent,
  },
  errorText: {
    color: Colors.accent,
    fontSize: 13,
  },
});
