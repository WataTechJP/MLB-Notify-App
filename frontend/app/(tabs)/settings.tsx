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
import { EventToggle } from "@/components/EventToggle";
import { Colors } from "@/constants/colors";

export default function SettingsScreen() {
  const { token } = usePushToken();
  const { players, preferences, isLoading, error, togglePlayer, toggleEvent, refresh } =
    usePreferences(token);

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
      <Text style={styles.heading}>設定</Text>

      {error && (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      )}

      {/* 通知イベント設定 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>通知するイベント</Text>
        <EventToggle
          label="⚾ ホームラン"
          description="選手がホームランを打ったとき通知"
          value={preferences?.event_prefs.home_run ?? false}
          onValueChange={(v) => toggleEvent("home_run", v)}
        />
        <EventToggle
          label="🔥 奪三振"
          description="選手が奪三振を記録したとき通知"
          value={preferences?.event_prefs.strikeout ?? false}
          onValueChange={(v) => toggleEvent("strikeout", v)}
        />
      </View>

      {/* 選手設定 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>
          フォローする選手 ({preferences?.player_ids.length ?? 0}/{players.length})
        </Text>
        {players.map((player) => (
          <PlayerCard
            key={player.id}
            player={player}
            isSubscribed={preferences?.player_ids.includes(player.id) ?? false}
            onToggle={() => togglePlayer(player.id)}
            showToggle={true}
          />
        ))}
      </View>
    </ScrollView>
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
