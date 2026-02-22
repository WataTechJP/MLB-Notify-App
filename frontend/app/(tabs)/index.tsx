import { useState } from "react";
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
import { PlayerEventModal } from "@/components/PlayerEventModal";
import { Colors } from "@/constants/colors";
import type { Player } from "@/types/api";

export default function HomeScreen() {
  const { token } = usePushToken();
  const { players, preferences, isLoading, error, togglePlayerEvent, refresh } =
    usePreferences(token);
  const [selectedPlayer, setSelectedPlayer] = useState<Player | null>(null);

  const subscribedPlayers = players.filter((p) =>
    preferences?.player_ids.includes(p.id)
  );

  const batters = subscribedPlayers.filter(
    (p) => p.position === "batter" || p.position === "two_way"
  );
  const pitchers = subscribedPlayers.filter(
    (p) => p.position === "pitcher" || p.position === "two_way"
  );

  if (isLoading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.accent} />
      </View>
    );
  }

  return (
    <>
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

        {/* 打者セクション */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>打者 ({batters.length})</Text>
          {batters.length === 0 ? (
            <View style={styles.emptyBox}>
              <Text style={styles.emptyText}>設定タブから選手を選んでください</Text>
            </View>
          ) : (
            batters.map((player) => (
              <PlayerCard
                key={player.id}
                player={player}
                isSubscribed={true}
                eventPrefs={preferences?.player_event_prefs[String(player.id)]}
                showToggle={false}
                onSettingsPress={() => setSelectedPlayer(player)}
              />
            ))
          )}
        </View>

        {/* 投手セクション */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>投手 ({pitchers.length})</Text>
          {pitchers.length === 0 ? (
            <View style={styles.emptyBox}>
              <Text style={styles.emptyText}>設定タブから選手を選んでください</Text>
            </View>
          ) : (
            pitchers.map((player) => (
              <PlayerCard
                key={player.id}
                player={player}
                isSubscribed={true}
                eventPrefs={preferences?.player_event_prefs[String(player.id)]}
                showToggle={false}
                onSettingsPress={() => setSelectedPlayer(player)}
              />
            ))
          )}
        </View>
      </ScrollView>

      <PlayerEventModal
        visible={selectedPlayer !== null}
        onClose={() => setSelectedPlayer(null)}
        player={selectedPlayer}
        playerEventPrefs={
          selectedPlayer
            ? (preferences?.player_event_prefs[String(selectedPlayer.id)] ?? {})
            : {}
        }
        onToggle={(eventType, value) => {
          if (selectedPlayer) {
            togglePlayerEvent(selectedPlayer.id, eventType, value);
          }
        }}
      />
    </>
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
